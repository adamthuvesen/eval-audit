"""Process, network, and paid-SDK modules stay banned outside their named owner files."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

PROBE = """import asyncio
import os
import subprocess
from urllib import request

subprocess.run(["true"], check=True)
os.system("true")
request.urlopen("x")
asyncio.run(asyncio.create_subprocess_exec("true"))
"""


def test_module_bans__fire_in_a_new_package_module(repo_root: Path) -> None:
    ruff = Path(sys.executable).parent / "ruff"
    done = subprocess.run(
        [str(ruff), "check", "--no-cache", "--stdin-filename", "eval_audit/new_module.py", "-"],
        cwd=repo_root,
        input=PROBE,
        capture_output=True,
        text=True,
        check=False,
    )
    banned = sorted(
        line.split("`")[1] for line in done.stdout.splitlines() if line.startswith("TID251")
    )
    assert banned == ["asyncio", "os.system", "subprocess", "urllib.request"], done.stdout


# Each owner may use only its own banned modules. pyproject.toml exempts owners from all of
# TID251, so this test reruns the ban with those exemptions cleared.
OWNER_ALLOWANCES = {
    "eval_audit/cli.py": {"subprocess"},
    "eval_audit/cli_templates.py": {"subprocess"},
    "tools/fixture_io.py": {"urllib.request"},
    "scouting/humaneval-direct-completion/run.py": {"subprocess", "urllib.request"},
    "scouting/humaneval-direct-completion/grade.py": {"subprocess"},
    ".agents/skills/verify-eval-audit/verify": {"subprocess"},
    "tests/**": {"subprocess", "urllib.request"},
}


def _owner(relative: str) -> str:
    if relative.startswith("tests/"):
        return "tests/**"
    return relative


def test_module_bans__owners_use_only_their_own_modules(repo_root: Path) -> None:
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    ignores = pyproject["tool"]["ruff"]["lint"]["per-file-ignores"]
    exempt = {pattern for pattern, rules in ignores.items() if "TID251" in rules}
    assert exempt == set(OWNER_ALLOWANCES), (
        "Every TID251 exemption in pyproject.toml needs an entry in OWNER_ALLOWANCES."
    )
    ruff = Path(sys.executable).parent / "ruff"
    owner_paths = [pattern.removesuffix("/**") for pattern in OWNER_ALLOWANCES]
    done = subprocess.run(
        [
            str(ruff),
            "check",
            "--no-cache",
            "--select",
            "TID251",
            "--config",
            "lint.per-file-ignores = {}",
            "--output-format",
            "json",
            *owner_paths,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    hits = json.loads(done.stdout)
    assert hits, done.stderr
    misplaced = sorted(
        f"{relative}: {banned}"
        for hit in hits
        for relative in [Path(hit["filename"]).relative_to(repo_root).as_posix()]
        for banned in [hit["message"].split("`")[1]]
        if banned not in OWNER_ALLOWANCES[_owner(relative)]
    )
    assert not misplaced, f"Banned modules outside their owner allowance: {misplaced}"
