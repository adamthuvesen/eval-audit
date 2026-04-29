"""rigor CLI — minimal entry points to reproduce the Exhibit A reanalysis.

Commands:
  rigor analyze STUDY_YAML            # write reports/<id>/analysis.json
  rigor report  STUDY_YAML            # validate then write reports/<id>/report.md
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import typer

from rigor.ingest.hal_gaia import HalGaiaAdapter
from rigor.ingest.synthetic import SyntheticAdapter
from rigor.report.markdown import render_report_to
from rigor.schema import StudySpec
from rigor.spec import render_study_spec
from rigor.stats import analyze

app = typer.Typer(no_args_is_help=True, add_completion=False)
spec_app = typer.Typer(no_args_is_help=True, help="Validate and render StudySpec files.")
app.add_typer(spec_app, name="spec")


@spec_app.command("validate")
def spec_validate_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Load STUDY_YAML through StudySpec.from_yaml; exit non-zero on validation failure."""
    from pydantic import ValidationError

    try:
        study = StudySpec.from_yaml(study_yaml)
    except ValidationError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2) from exc
    typer.echo(f"OK: {study.id}")


@spec_app.command("render")
def spec_render_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", help="Destination markdown file."),
    fmt: str = typer.Option("markdown", "--format", help="Output format. Only 'markdown' is supported in v0."),
) -> None:
    """Render STUDY_YAML to a deterministic markdown rendition at --out."""
    if fmt != "markdown":
        typer.echo(
            f"--format={fmt!r} is not supported in v0. "
            "Only 'markdown' is implemented. HTML rendering is a planned follow-up.",
            err=True,
        )
        raise typer.Exit(code=2)

    study = StudySpec.from_yaml(study_yaml)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_study_spec(study))
    typer.echo(f"wrote {out}")

_ADAPTERS: dict[str, Callable[[], object]] = {
    "gaia": HalGaiaAdapter,
    "synthetic": SyntheticAdapter,
}


def _resolve_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    here = Path(__file__).resolve()
    return here.parent.parent


def _load_runs(study: StudySpec, repo_root: Path):
    if study.benchmark not in _ADAPTERS:
        raise typer.BadParameter(
            f"no ingest adapter for benchmark={study.benchmark!r}; known: {sorted(_ADAPTERS)}"
        )
    adapter = _ADAPTERS[study.benchmark]()
    if study.benchmark == "synthetic":
        source = repo_root / "scouting" / "synthetic"
    else:
        source = repo_root / "scouting" / "candidates" / study.benchmark
    return adapter.load(source)


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _fixture_sha256(study: StudySpec, repo_root: Path) -> str:
    if study.benchmark == "synthetic":
        path = repo_root / "scouting" / "synthetic" / "runs.parquet"
    else:
        path = repo_root / "scouting" / "candidates" / study.benchmark / "sample.parquet"
    if not path.exists():
        return "n/a"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _run_synthetic_validation_gate(repo_root: Path) -> bool:
    """Invoke the synthetic-validation pytest suite. Returns True on pass."""
    cmd = [
        "uv", "run", "pytest", "-q",
        "-m", "synthetic_validation",
        str(repo_root / "tests" / "synthetic_validation"),
    ]
    typer.echo("running synthetic-validation gate (pytest -m synthetic_validation)...")
    result = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr, err=True)
    return result.returncode == 0


def _serialise_result(result) -> dict:
    out = dataclasses.asdict(result)
    if isinstance(out.get("pareto_frontier"), set):
        out["pareto_frontier"] = sorted(out["pareto_frontier"])
    return out


@app.command(name="analyze")
def analyze_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    out_dir: Path = typer.Option(Path("reports"), "--out-dir"),
    repo_root: Path | None = typer.Option(None, "--repo-root"),
    bootstrap_iterations: int = typer.Option(10_000, "--bootstrap-iterations"),
    bootstrap_seed: int = typer.Option(42, "--bootstrap-seed"),
) -> None:
    """Run analysis end-to-end and write `reports/<id>/analysis.json`."""
    root = _resolve_repo_root(repo_root)
    study = StudySpec.from_yaml(study_yaml)
    runs = _load_runs(study, root)
    result = analyze(
        study,
        runs,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    target_dir = out_dir / study.id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "analysis.json"
    target.write_text(json.dumps(_serialise_result(result), indent=2, default=str) + "\n")
    typer.echo(f"wrote {target}")


@app.command(name="report")
def report_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    out_dir: Path = typer.Option(Path("reports"), "--out-dir"),
    repo_root: Path | None = typer.Option(None, "--repo-root"),
    skip_validation: bool = typer.Option(False, "--skip-validation"),
    bootstrap_iterations: int = typer.Option(10_000, "--bootstrap-iterations"),
    bootstrap_seed: int = typer.Option(42, "--bootstrap-seed"),
) -> None:
    """Run validation gate, then write `reports/<id>/report.md`."""
    root = _resolve_repo_root(repo_root)

    if skip_validation:
        typer.echo(
            "WARNING: synthetic validation skipped (--skip-validation). "
            "The report contract requires this gate to pass before any Exhibit A render. "
            "This run is for development/debug only; do NOT publish the resulting report."
        )
    else:
        gate_ok = _run_synthetic_validation_gate(root)
        if not gate_ok:
            typer.echo("synthetic-validation gate FAILED; refusing to write report.", err=True)
            raise typer.Exit(code=1)

    study = StudySpec.from_yaml(study_yaml)
    runs = _load_runs(study, root)

    target_dir = out_dir / study.id
    target = target_dir / "report.md"
    render_report_to(
        target,
        study,
        runs,
        clock=lambda: datetime.now(UTC),
        git_commit=_git_commit(root),
        fixture_sha256=_fixture_sha256(study, root),
        repo_root=root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    typer.echo(f"wrote {target}")


if __name__ == "__main__":
    app()
