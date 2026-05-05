"""eval-audit CLI — minimal entry points to reproduce the Exhibit A reanalysis.

Commands:
  eval-audit analyze STUDY_YAML            # write reports/<id>/analysis.json
  eval-audit report  STUDY_YAML            # validate then write reports/<id>/report.md
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import typer

from eval_audit.cli_templates import SLUG_RE, ScaffoldError, scaffold_byo_study
from eval_audit.fixtures import benchmark_dir_name
from eval_audit.ingest import IngestContractError
from eval_audit.ingest.generic import load_run_records
from eval_audit.ingest.hal_gaia import HalGaiaAdapter
from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
from eval_audit.ingest.synthetic import SyntheticAdapter
from eval_audit.report.markdown import render_report_to
from eval_audit.schema import StudySpec
from eval_audit.spec import render_study_spec
from eval_audit.stats import analyze


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(importlib.metadata.version("eval-audit"))
        raise typer.Exit(code=0)


app = typer.Typer(no_args_is_help=True, add_completion=False)
spec_app = typer.Typer(no_args_is_help=True, help="Validate and render StudySpec files.")
app.add_typer(spec_app, name="spec")


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the eval-audit package version and exit.",
    ),
) -> None:
    """eval-audit — verdict-grade audit reports for AI benchmark claims."""
    # Body intentionally empty; the callback exists to host the --version flag.
    return


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
    "tau_bench": HalTauBenchAdapter,
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
        source = (
            repo_root / "scouting" / "candidates" / benchmark_dir_name(study.benchmark)
        )
    return adapter.load(source)


def _resolve_runs_frame(study: StudySpec, repo_root: Path, runs_override: Path | None):
    """Pick between the BYO --runs file and the benchmark-keyed adapter path."""
    if runs_override is None:
        return _load_runs(study, repo_root)
    if not runs_override.exists():
        typer.echo(
            f"--runs path does not exist: {runs_override}",
            err=True,
        )
        raise typer.Exit(code=1)
    return load_run_records(runs_override)


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _fixture_sha256(
    study: StudySpec, repo_root: Path, runs_override: Path | None = None
) -> str:
    if runs_override is not None:
        path = runs_override
    elif study.benchmark == "synthetic":
        path = repo_root / "scouting" / "synthetic" / "runs.parquet"
    else:
        path = (
            repo_root
            / "scouting"
            / "candidates"
            / benchmark_dir_name(study.benchmark)
            / "sample.parquet"
        )
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
    runs: Path | None = typer.Option(
        None,
        "--runs",
        help=(
            "Path to a canonical RunRecord-shaped parquet. When provided, "
            "bypasses the benchmark-keyed adapter and loads this file directly."
        ),
    ),
    bootstrap_iterations: int = typer.Option(10_000, "--bootstrap-iterations", min=1),
    bootstrap_seed: int = typer.Option(42, "--bootstrap-seed"),
) -> None:
    """Run analysis end-to-end and write `reports/<id>/analysis.json`."""
    root = _resolve_repo_root(repo_root)
    study = StudySpec.from_yaml(study_yaml)
    runs_frame = _resolve_runs_frame(study, root, runs)
    result = analyze(
        study,
        runs_frame,
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
    runs: Path | None = typer.Option(
        None,
        "--runs",
        help=(
            "Path to a canonical RunRecord-shaped parquet. When provided, "
            "bypasses the benchmark-keyed adapter and loads this file directly."
        ),
    ),
    skip_validation: bool = typer.Option(False, "--skip-validation"),
    bootstrap_iterations: int = typer.Option(10_000, "--bootstrap-iterations", min=1),
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
    runs_frame = _resolve_runs_frame(study, root, runs)

    target_dir = out_dir / study.id
    target = target_dir / "report.md"
    render_report_to(
        target,
        study,
        runs_frame,
        clock=lambda: datetime.now(UTC),
        git_commit=_git_commit(root),
        fixture_sha256=_fixture_sha256(study, root, runs),
        repo_root=root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    typer.echo(f"wrote {target}")


@app.command(name="init")
def init_cmd(
    name: str = typer.Argument(..., help="Kebab-case slug for the new BYO study."),
    cwd: Path = typer.Option(
        None,
        "--cwd",
        help="Working directory (defaults to the user's CWD; primarily for tests).",
    ),
) -> None:
    """Scaffold a new BYO study directory at ./<name>/."""
    if not SLUG_RE.match(name):
        typer.echo(
            f"invalid slug {name!r}: name must match ^[a-z0-9][a-z0-9-]*$ "
            "(e.g. 'my-study'). Lowercase letters, digits, and hyphens only; "
            "must start with a letter or digit.",
            err=True,
        )
        raise typer.Exit(code=2)

    base = cwd if cwd is not None else Path.cwd()
    target = base / name
    if target.exists() and any(target.iterdir()):
        typer.echo(
            f"target directory is not empty: {target}. "
            "Refusing to clobber existing files. "
            "Remove the directory yourself if you want to start over.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        scaffold_byo_study(target, study_id=name)
    except ScaffoldError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"created {target.resolve()}")


@app.command(name="validate")
def validate_cmd(
    runs: Path = typer.Argument(..., help="Path to a canonical RunRecord-shaped parquet."),
    study: Path = typer.Argument(..., help="Path to a StudySpec YAML file."),
) -> None:
    """Pre-flight check: validate a runs parquet and a study YAML in isolation."""
    from pydantic import ValidationError

    if not runs.exists():
        typer.echo(f"runs path does not exist: {runs}", err=True)
        raise typer.Exit(code=1)
    try:
        frame = load_run_records(runs)
    except IngestContractError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if not study.exists():
        typer.echo(f"study path does not exist: {study}", err=True)
        raise typer.Exit(code=1)
    try:
        study_spec = StudySpec.from_yaml(study)
    except ValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"OK: {frame.height} rows, study {study_spec.id!r}")


if __name__ == "__main__":
    app()
