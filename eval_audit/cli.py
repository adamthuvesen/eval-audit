"""eval-audit CLI — minimal entry points to reproduce the GAIA HAL Generalist reanalysis.

Commands:
  eval-audit analyze STUDY_YAML            # write reports/<id>/analysis.json
  eval-audit report  STUDY_YAML            # validate then write reports/<id>/report.md
"""

from __future__ import annotations

import importlib.metadata
import json
import shlex
import subprocess
from collections.abc import Callable
from functools import wraps
from pathlib import Path

import typer
from polars.exceptions import PolarsError
from pydantic import BaseModel, ValidationError
from yaml import YAMLError

from eval_audit.artifacts import audit_directory, publish_artifacts
from eval_audit.checks import (
    ReadinessStatus,
    check_paths,
    readiness_from_diagnostics,
    render_readiness_text,
)
from eval_audit.cli_templates import SLUG_RE, ScaffoldError, scaffold_byo_study
from eval_audit.errors import AnalysisInputError
from eval_audit.ingest import IngestContractError
from eval_audit.ingest.generic import load_run_records
from eval_audit.pipeline import (
    GateOptionError,
    UnsupportedBenchmarkError,
    allowed_gate_verdicts,
    analysis_json_bytes,
    build_audit,
    claim_verdicts,
    gate,
    gate_output_text,
    load_evidence,
    validated_min_readiness,
)
from eval_audit.portfolio import (
    load_portfolio_rows,
    portfolio_json_bytes,
    render_portfolio_markdown,
)
from eval_audit.report import ReportContractError
from eval_audit.schema import RunRecord, StudySpec
from eval_audit.schema.audit_summary import AuditSummary
from eval_audit.spec import render_study_spec
from eval_audit.stats import analyze


def _cli_errors[**P](command: Callable[P, None]) -> Callable[P, None]:
    @wraps(command)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            command(*args, **kwargs)
        except (
            OSError,
            ValueError,
            YAMLError,
            PolarsError,
            IngestContractError,
            AnalysisInputError,
            ReportContractError,
        ) as exc:
            if kwargs.get("json_output"):
                typer.echo(
                    json.dumps(
                        {"status": "fail", "failures": [{"type": "input", "message": str(exc)}]},
                        allow_nan=False,
                    )
                )
            elif isinstance(exc, AnalysisInputError) and exc.diagnostics:
                typer.echo("evidence readiness check FAILED", err=True)
                typer.echo(
                    render_readiness_text(readiness_from_diagnostics(None, exc.diagnostics)),
                    err=True,
                    nl=False,
                )
                study_path, runs_path = kwargs.get("study_yaml"), kwargs.get("runs")
                if isinstance(study_path, Path) and isinstance(runs_path, Path):
                    study_id = StudySpec.from_yaml(study_path).id
                    output_root = kwargs.get("out_dir", Path("reports"))
                    if isinstance(output_root, Path):
                        check_path = audit_directory(output_root, study_id) / "check.json"
                        typer.echo(
                            "For full diagnostics, run:\n  "
                            + shlex.join(
                                [
                                    "eval-audit",
                                    "check",
                                    str(study_path),
                                    "--runs",
                                    str(runs_path),
                                    "--out",
                                    str(check_path),
                                ]
                            ),
                            err=True,
                        )
            else:
                prefix = (
                    "invalid study YAML"
                    if isinstance(exc, (ValidationError, YAMLError))
                    else command.__name__.removesuffix("_cmd")
                )
                typer.echo(f"{prefix}: {exc}", err=True)
            raise typer.Exit(
                code=2
                if isinstance(exc, (ValidationError, YAMLError, UnsupportedBenchmarkError))
                else 1
            ) from exc

    return wrapped


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


def _load_study_or_exit(study_yaml: Path) -> StudySpec:
    try:
        return StudySpec.from_yaml(study_yaml)
    except (OSError, ValidationError, ValueError, YAMLError) as exc:
        typer.echo(f"invalid study YAML {study_yaml}: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@spec_app.command("validate")
@_cli_errors
def spec_validate_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Load STUDY_YAML through StudySpec.from_yaml; exit non-zero on validation failure."""
    study = _load_study_or_exit(study_yaml)
    typer.echo(f"OK: {study.id}")


@spec_app.command("schema")
@_cli_errors
def spec_schema_cmd(
    model: str = typer.Option(
        "study", "--model", help="Contract to inspect: study, run, or summary."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Write JSON Schema to this file instead of stdout."
    ),
) -> None:
    """Derive the machine-readable contract from its authoritative Pydantic model."""
    models: dict[str, type[BaseModel]] = {
        "study": StudySpec,
        "run": RunRecord,
        "summary": AuditSummary,
    }
    if model not in models:
        raise typer.BadParameter("--model must be study, run, or summary")
    content = (
        json.dumps(models[model].model_json_schema(), allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    )
    if out is None:
        typer.echo(content, nl=False)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)
        typer.echo(f"wrote {out}")


@spec_app.command("render")
@_cli_errors
def spec_render_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", help="Destination markdown file."),
    fmt: str = typer.Option(
        "markdown", "--format", help="Output format. Only 'markdown' is supported in v0."
    ),
) -> None:
    """Render STUDY_YAML to a deterministic markdown rendition at --out."""
    if fmt != "markdown":
        typer.echo(
            f"--format={fmt!r} is not supported in v0. "
            "Only 'markdown' is implemented. HTML rendering is a planned follow-up.",
            err=True,
        )
        raise typer.Exit(code=2)

    study = _load_study_or_exit(study_yaml)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_study_spec(study))
    typer.echo(f"wrote {out}")


def _resolve_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    here = Path(__file__).resolve()
    return here.parent.parent


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except subprocess.CalledProcessError, FileNotFoundError:
        return "unknown"


def _gate_options(
    min_readiness: str, allow_verdict: list[str] | None
) -> tuple[ReadinessStatus, list[str]]:
    try:
        return validated_min_readiness(min_readiness), allowed_gate_verdicts(allow_verdict)
    except GateOptionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


@app.command(name="analyze")
@_cli_errors
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
    study = _load_study_or_exit(study_yaml)
    runs_frame, _source = load_evidence(study, root, runs)
    result = analyze(
        study,
        runs_frame,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    target_dir = audit_directory(out_dir, study.id)
    publish_artifacts(target_dir, {"analysis.json": analysis_json_bytes(result)}, complete=False)
    typer.echo(f"wrote {target_dir / 'analysis.json'}")


@app.command(name="audit")
@_cli_errors
def audit_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    runs: Path = typer.Option(
        ...,
        "--runs",
        help="Path to a canonical RunRecord-shaped parquet.",
    ),
    out_dir: Path = typer.Option(Path("reports"), "--out-dir"),
    repo_root: Path | None = typer.Option(None, "--repo-root"),
    bootstrap_iterations: int = typer.Option(10_000, "--bootstrap-iterations", min=1),
    bootstrap_seed: int = typer.Option(42, "--bootstrap-seed"),
    html: bool = typer.Option(
        False,
        "--html",
        help="Also write a structured static HTML report beside report.md.",
    ),
) -> None:
    """Validate, check readiness, analyze, and write check.json, analysis.json, report.md, and summary.json."""
    root = _resolve_repo_root(repo_root)
    study = _load_study_or_exit(study_yaml)
    runs_frame, source = load_evidence(study, root, runs)
    products = build_audit(
        study,
        runs_frame,
        study_path=study_yaml,
        source=source,
        repo_root=root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
        git_commit=_git_commit(root),
        html=html,
    )
    target_dir = audit_directory(out_dir, study.id)
    publish_artifacts(target_dir, products.artifacts, complete=True)
    typer.echo(f"audit passed: study={study.id} readiness={products.readiness.status}")
    for name in products.artifacts:
        typer.echo(f"wrote {target_dir / name}")
    for verdict in claim_verdicts(products.result, study):
        typer.echo(f"claim {verdict['claim_id']}: {verdict['verdict']}")


@app.command(name="gate")
@_cli_errors
def gate_cmd(
    study_yaml: Path = typer.Argument(..., dir_okay=False),
    runs: Path = typer.Option(
        ...,
        "--runs",
        help="Path to a canonical RunRecord-shaped parquet.",
    ),
    repo_root: Path | None = typer.Option(None, "--repo-root"),
    min_readiness: str = typer.Option(
        "ready_with_warnings",
        "--min-readiness",
        help="Minimum readiness status: ready_with_warnings or ready.",
    ),
    allow_verdict: list[str] | None = typer.Option(
        None,
        "--allow-verdict",
        help="Allowed decision-impact verdict. Repeat to allow multiple verdicts.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print deterministic gate JSON instead of human text.",
    ),
    bootstrap_iterations: int = typer.Option(10_000, "--bootstrap-iterations", min=1),
    bootstrap_seed: int = typer.Option(42, "--bootstrap-seed"),
) -> None:
    """CI-friendly gate over evidence readiness and claim verdicts."""
    minimum, allowed_verdicts = _gate_options(min_readiness, allow_verdict)
    root = _resolve_repo_root(repo_root)
    study = StudySpec.from_yaml(study_yaml)
    runs_frame, source = load_evidence(study, root, runs)
    payload = gate(
        study,
        runs_frame,
        source=source,
        repo_root=root,
        min_readiness=minimum,
        allowed_verdicts=allowed_verdicts,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    typer.echo(gate_output_text(payload, json_output=json_output), nl=False)
    if payload["failures"]:
        raise typer.Exit(code=1)


@app.command(name="portfolio")
@_cli_errors
def portfolio_cmd(
    reports_dir: Path = typer.Argument(..., help="Directory containing completed audit reports."),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Destination Markdown evidence-index file.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print deterministic portfolio JSON instead of Markdown.",
    ),
) -> None:
    """Render an evidence index from completed audit summary.json artifacts."""
    rows = load_portfolio_rows(reports_dir)
    if not rows:
        typer.echo(
            f"no inspectable audit report directories under {reports_dir}",
            err=True,
        )
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(portfolio_json_bytes(rows).decode(), nl=False)
        return

    markdown = render_portfolio_markdown(rows, reports_dir)
    if out is None:
        typer.echo(markdown, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown)
    typer.echo(f"wrote {out}")


@app.command(name="report")
@_cli_errors
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
    study = _load_study_or_exit(study_yaml)

    if skip_validation:
        typer.echo(
            "--skip-validation is deprecated. Evidence validation always runs; synthetic recovery runs in make slow.",
            err=True,
        )
    runs_frame, source = load_evidence(study, root, runs)
    products = build_audit(
        study,
        runs_frame,
        study_path=study_yaml,
        source=source,
        repo_root=root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
        git_commit=_git_commit(root),
    )
    target_dir = audit_directory(out_dir, study.id)
    publish_artifacts(target_dir, products.artifacts, complete=True)
    for name in products.artifacts:
        typer.echo(f"wrote {target_dir / name}")


@app.command(name="init")
@_cli_errors
def init_cmd(
    name: str = typer.Argument(..., help="Kebab-case slug for the new BYO study."),
    cwd: Path | None = typer.Option(
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
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
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


@app.command(name="check")
@_cli_errors
def check_cmd(
    study_yaml: Path = typer.Argument(..., help="Path to a StudySpec YAML file."),
    runs: Path = typer.Option(
        ...,
        "--runs",
        help="Path to a canonical RunRecord-shaped parquet.",
    ),
    repo_root: Path | None = typer.Option(None, "--repo-root"),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print deterministic readiness JSON instead of human text.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Optional destination for deterministic readiness JSON.",
    ),
) -> None:
    """Audit-readiness gate for a declared comparison."""
    root = _resolve_repo_root(repo_root)
    readiness = check_paths(study_yaml, runs, repo_root=root)
    json_bytes = readiness.to_json_bytes()

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(json_bytes)

    if json_output:
        typer.echo(json_bytes.decode(), nl=False)
    else:
        typer.echo(render_readiness_text(readiness), nl=False)

    if readiness.status == "not_ready":
        raise typer.Exit(code=1)


@app.command(name="validate")
@_cli_errors
def validate_cmd(
    runs: Path = typer.Argument(..., help="Path to a canonical RunRecord-shaped parquet."),
    study: Path = typer.Argument(..., help="Path to a StudySpec YAML file."),
) -> None:
    """Pre-flight check: validate a runs parquet and a study YAML in isolation."""
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
    study_spec = _load_study_or_exit(study)

    typer.echo(f"OK: {frame.height} rows, study {study_spec.id!r}")


if __name__ == "__main__":
    app()
