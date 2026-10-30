"""Exercise the installed wheel without the checkout or development dependencies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_wheel__runtime_only_external_environment(repo_root: Path, tmp_path: Path) -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}
    }

    def run(args: list[str], *, cwd: Path = tmp_path) -> str:
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, f"{args!r}\n{result.stdout}\n{result.stderr}"
        return result.stdout

    assert not tmp_path.is_relative_to(repo_root)
    run(["uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist")], cwd=repo_root)
    (wheel,) = (tmp_path / "dist").glob("eval_audit-*.whl")
    requirements = tmp_path / "pylock.toml"
    requirements.write_text(
        run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "pylock.toml",
            ],
            cwd=repo_root,
        )
    )
    environment = tmp_path / "runtime"
    run(["uv", "venv", "--python", sys.executable, str(environment)])
    python = environment / "bin" / "python"
    cli = environment / "bin" / "eval-audit"
    run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "-r",
            str(requirements),
        ]
    )
    run(["uv", "pip", "install", "--offline", "--no-deps", "--python", str(python), str(wheel)])
    package_path = run(
        [
            str(python),
            "-I",
            "-c",
            "import importlib.util, eval_audit; "
            "assert importlib.util.find_spec('pytest') is None; "
            "print(eval_audit.__file__)",
        ]
    ).strip()
    assert Path(package_path).is_relative_to(environment)
    assert run([str(cli), "--version"]).strip()
    run([str(cli), "init", "wheel-study", "--cwd", "."])
    study_dir = tmp_path / "wheel-study"
    study = study_dir / "study.yaml"
    runs = study_dir / "runs.parquet"
    run([str(cli), "validate", str(runs), str(study)])
    reports = tmp_path / "reports"
    common = [str(study), "--runs", str(runs), "--repo-root", str(tmp_path)]
    run([str(cli), "audit", *common, "--out-dir", str(reports), "--bootstrap-iterations", "200"])
    run([str(cli), "report", *common, "--out-dir", str(reports), "--bootstrap-iterations", "200"])
    gate = json.loads(
        run(
            [
                str(cli),
                "gate",
                *common,
                "--allow-verdict",
                "switch",
                "--allow-verdict",
                "hold",
                "--bootstrap-iterations",
                "200",
                "--json",
            ]
        )
    )
    assert gate["status"] == "pass"
    portfolio = json.loads(run([str(cli), "portfolio", str(reports), "--json"]))
    assert portfolio
    assert (reports / "wheel-study" / "report.md").is_file()
