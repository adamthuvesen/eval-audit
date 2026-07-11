"""eval-audit CLI — minimal entry points to reproduce the GAIA HAL Generalist reanalysis.

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
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import polars as pl
import typer
from pydantic import ValidationError
from yaml import YAMLError

from eval_audit.checks import (
    ReadinessCheck,
    ReadinessResult,
    ReadinessStatus,
    check_evidence,
    check_paths,
    render_readiness_text,
)
from eval_audit.cli_templates import SLUG_RE, ScaffoldError, scaffold_byo_study
from eval_audit.fixtures import benchmark_dir_name
from eval_audit.ingest import IngestAdapter, IngestContractError
from eval_audit.ingest.generic import load_run_records
from eval_audit.ingest.hal_gaia import HalGaiaAdapter
from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
from eval_audit.ingest.swe_bench_verified import SweBenchVerifiedAdapter
from eval_audit.ingest.synthetic import SyntheticAdapter
from eval_audit.ingest.terminal_bench import TerminalBenchMuxAdapter
from eval_audit.pipeline import (
    claim_verdicts,
    render_audit_markdown,
    run_analysis,
    run_readiness,
    write_analysis_json,
    write_check_json,
    write_summary_json,
)
from eval_audit.portfolio import (
    load_portfolio_rows,
    portfolio_json_bytes,
    render_portfolio_markdown,
)
from eval_audit.report.decisions import DECISION_IMPACT_VOCAB
from eval_audit.report.html import render_html_report
from eval_audit.report.markdown import render_report_to
from eval_audit.schema import StudySpec
from eval_audit.spec import render_study_spec

_READINESS_RANK: dict[ReadinessStatus, int] = {
    "not_ready": 0,
    "ready_with_warnings": 1,
    "ready": 2,
}
_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


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
    except (ValidationError, ValueError, YAMLError) as exc:
        typer.echo(f"invalid study YAML {study_yaml}: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@spec_app.command("validate")
def spec_validate_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    """Load STUDY_YAML through StudySpec.from_yaml; exit non-zero on validation failure."""
    study = _load_study_or_exit(study_yaml)
    typer.echo(f"OK: {study.id}")


@spec_app.command("render")
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


_ADAPTERS: dict[str, Callable[[], IngestAdapter]] = {
    "gaia": HalGaiaAdapter,
    "synthetic": SyntheticAdapter,
    "tau_bench": HalTauBenchAdapter,
    "swe-bench-verified": SweBenchVerifiedAdapter,
    "terminal-bench-2": TerminalBenchMuxAdapter,
}

# Benchmarks whose committed fixture lives under `examples/<study.id>/` rather
# than `scouting/candidates/<benchmark>/`. Public-submission re-analyses ship
# their canonical RunRecord parquet inside the repo (see scouting-fixtures
# capability spec) because the upstream artifacts (e.g. S3-hosted submission
# logs) are not committed.
_EXAMPLES_BACKED_BENCHMARKS: frozenset[str] = frozenset({"swe-bench-verified", "terminal-bench-2"})


@dataclasses.dataclass(frozen=True)
class _FixtureSource:
    adapter_factory: Callable[[], IngestAdapter]
    source_dir: Path
    parquet_path: Path


def _resolve_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    here = Path(__file__).resolve()
    return here.parent.parent


def _fixture_source(study: StudySpec, repo_root: Path) -> _FixtureSource:
    if study.benchmark not in _ADAPTERS:
        raise typer.BadParameter(
            f"no benchmark-keyed ingest adapter for benchmark={study.benchmark!r}. "
            "Pass --runs PATH for canonical BYO RunRecord parquet, or use one "
            f"of the adapter-backed benchmarks: {sorted(_ADAPTERS)}"
        )
    if study.benchmark == "synthetic":
        source = repo_root / "scouting" / "synthetic"
        parquet_name = "runs.parquet"
    elif study.benchmark in _EXAMPLES_BACKED_BENCHMARKS:
        source = repo_root / "examples" / study.id
        parquet_name = "runs.parquet"
    else:
        source = repo_root / "scouting" / "candidates" / benchmark_dir_name(study.benchmark)
        parquet_name = "sample.parquet"
    return _FixtureSource(
        adapter_factory=_ADAPTERS[study.benchmark],
        source_dir=source,
        parquet_path=source / parquet_name,
    )


def _load_runs(study: StudySpec, repo_root: Path) -> pl.DataFrame:
    source = _fixture_source(study, repo_root)
    adapter = source.adapter_factory()
    return adapter.load(source.source_dir)


def _resolve_runs_frame(
    study: StudySpec, repo_root: Path, runs_override: Path | None
) -> pl.DataFrame:
    """Pick between the BYO --runs file and the benchmark-keyed adapter path."""
    if runs_override is None:
        return _load_runs(study, repo_root)
    if not runs_override.exists():
        typer.echo(
            f"--runs path does not exist: {runs_override}",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        return load_run_records(runs_override)
    except IngestContractError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _fixture_sha256(study: StudySpec, repo_root: Path, runs_override: Path | None = None) -> str:
    if runs_override is not None:
        path = runs_override
    else:
        path = _fixture_source(study, repo_root).parquet_path
    if not path.exists():
        return "n/a"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _run_synthetic_validation_gate(repo_root: Path) -> bool:
    """Invoke the synthetic-validation pytest suite. Returns True on pass."""
    cmd = [
        "uv",
        "run",
        "pytest",
        "-q",
        "-m",
        "synthetic_validation",
        str(repo_root / "tests" / "synthetic_validation"),
    ]
    typer.echo("running synthetic-validation gate (pytest -m synthetic_validation)...")
    try:
        result = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    except FileNotFoundError:
        fallback = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-m",
            "synthetic_validation",
            str(repo_root / "tests" / "synthetic_validation"),
        ]
        result = subprocess.run(fallback, cwd=str(repo_root), capture_output=True, text=True)
    typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr, err=True)
    return result.returncode == 0


def _write_markdown_report(
    text: str,
    target_dir: Path,
) -> Path:
    target = target_dir / "report.md"
    target.write_text(text)
    return target


def _write_html_report(markdown_text: str, study: StudySpec, target_dir: Path) -> Path:
    target = target_dir / "report.html"
    target.write_text(render_html_report(markdown_text, title=f"{study.id} audit report"))
    return target


def _failed_checks(readiness: ReadinessResult) -> list[ReadinessCheck]:
    return [check for check in readiness.checks if check.status == "fail"]


def _most_important_failed_check(readiness: ReadinessResult) -> ReadinessCheck | None:
    failed = _failed_checks(readiness)
    if not failed:
        return None
    return min(
        enumerate(failed),
        key=lambda item: (_SEVERITY_RANK[item[1].severity], item[0]),
    )[1]


def _readiness_meets_minimum(
    readiness: ReadinessStatus,
    minimum: ReadinessStatus,
) -> bool:
    return _READINESS_RANK[readiness] >= _READINESS_RANK[minimum]


def _validated_min_readiness(value: str) -> ReadinessStatus:
    if value not in {"ready", "ready_with_warnings"}:
        typer.echo(
            "--min-readiness must be one of: ready, ready_with_warnings",
            err=True,
        )
        raise typer.Exit(code=2)
    return cast(ReadinessStatus, value)


def _allowed_gate_verdicts(allow_verdict: list[str] | None) -> list[str]:
    requested_verdicts = list(allow_verdict or DECISION_IMPACT_VOCAB)
    unknown = sorted(set(requested_verdicts) - set(DECISION_IMPACT_VOCAB))
    if unknown:
        typer.echo(
            "unsupported verdict name(s): "
            f"{', '.join(unknown)}. Controlled vocabulary: "
            f"{', '.join(DECISION_IMPACT_VOCAB)}",
            err=True,
        )
        raise typer.Exit(code=2)
    return requested_verdicts


def _readiness_gate_failures(
    readiness: ReadinessResult,
    min_readiness: ReadinessStatus,
) -> list[dict[str, object]]:
    if readiness.status == "not_ready":
        return [
            {
                "type": "readiness",
                "check_id": check.id,
                "severity": check.severity,
                "message": check.message,
                "fix_suggestion": check.fix_suggestion,
            }
            for check in _failed_checks(readiness)
        ]
    if not _readiness_meets_minimum(readiness.status, min_readiness):
        return [
            {
                "type": "readiness",
                "message": (f"readiness {readiness.status} does not meet minimum {min_readiness}"),
            }
        ]
    return []


def _verdict_gate_failures(
    claims: list[dict[str, str]],
    allowed_verdicts: list[str],
) -> list[dict[str, object]]:
    return [
        {
            "type": "verdict",
            "claim_id": claim["claim_id"],
            "verdict": claim["verdict"],
            "allowed_verdicts": allowed_verdicts,
        }
        for claim in claims
        if claim["verdict"] not in allowed_verdicts
    ]


def _gate_claims_and_failures(
    *,
    study: StudySpec,
    runs_frame: pl.DataFrame,
    readiness: ReadinessResult,
    min_readiness: ReadinessStatus,
    allowed_verdicts: list[str],
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    readiness_failures = _readiness_gate_failures(readiness, min_readiness)
    if readiness_failures:
        return [], readiness_failures

    result = run_analysis(
        study,
        runs_frame,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    claims = claim_verdicts(result, study)
    return claims, _verdict_gate_failures(claims, allowed_verdicts)


def _emit_gate_output(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        typer.echo(
            json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
            nl=False,
        )
        return

    typer.echo(
        f"gate {payload['status']}: study={payload['study_id']} readiness={payload['readiness']}"
    )
    claims = payload["claims"]
    failures = payload["failures"]
    if isinstance(claims, list):
        for claim in claims:
            typer.echo(f"claim {claim['claim_id']}: {claim['verdict']}")
    if isinstance(failures, list):
        for failure in failures:
            if failure["type"] == "verdict":
                typer.echo(
                    "failure: claim "
                    f"{failure['claim_id']} verdict {failure['verdict']} "
                    "not in allowed verdicts "
                    f"{', '.join(failure['allowed_verdicts'])}"
                )
            elif "check_id" in failure:
                typer.echo(
                    f"failure: {failure['check_id']}: "
                    f"{failure['message']}; fix: {failure['fix_suggestion']}"
                )
            else:
                typer.echo(f"failure: {failure['message']}")


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
    study = _load_study_or_exit(study_yaml)
    runs_frame = _resolve_runs_frame(study, root, runs)
    result = run_analysis(
        study,
        runs_frame,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    target_dir = out_dir / study.id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = write_analysis_json(result, target_dir)
    typer.echo(f"wrote {target}")


@app.command(name="audit")
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
    runs_frame = _resolve_runs_frame(study, root, runs)
    readiness = run_readiness(study_yaml, runs, study, runs_frame, repo_root=root)
    if readiness.status == "not_ready":
        important = _most_important_failed_check(readiness)
        failed_ids = ", ".join(check.id for check in _failed_checks(readiness))
        typer.echo(f"audit failed: study={study.id} readiness={readiness.status}", err=True)
        if failed_ids:
            typer.echo(f"failed readiness checks: {failed_ids}", err=True)
        if important is not None:
            typer.echo(
                f"highest-severity fix: {important.id}: {important.fix_suggestion}",
                err=True,
            )
        raise typer.Exit(code=1)

    target_dir = out_dir / study.id
    target_dir.mkdir(parents=True, exist_ok=True)
    check_path, check_sha256 = write_check_json(readiness, target_dir)
    result = run_analysis(
        study,
        runs_frame,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    analysis_path = write_analysis_json(result, target_dir)
    markdown_text = render_audit_markdown(
        result,
        study,
        runs_frame,
        repo_root=root,
        runs_path=runs,
        readiness=readiness,
        check_sha256=check_sha256,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
        git_commit=_git_commit(root),
        fixture_sha256=_fixture_sha256(study, root, runs),
        deterministic_clock=True,
    )
    report_path = _write_markdown_report(markdown_text, target_dir)
    html_path: Path | None = None
    if html:
        html_path = _write_html_report(markdown_text, study, target_dir)
    summary_path = write_summary_json(
        result=result,
        study=study,
        runs_frame=runs_frame,
        readiness=readiness,
        repo_root=root,
        target_dir=target_dir,
        check_path=check_path,
        analysis_path=analysis_path,
        report_path=report_path,
        html_path=html_path,
    )

    verdicts = claim_verdicts(result, study)
    typer.echo(f"audit passed: study={study.id} readiness={readiness.status}")
    typer.echo(f"wrote {check_path}")
    typer.echo(f"wrote {analysis_path}")
    typer.echo(f"wrote {report_path}")
    if html_path is not None:
        typer.echo(f"wrote {html_path}")
    typer.echo(f"wrote {summary_path}")
    for verdict in verdicts:
        typer.echo(f"claim {verdict['claim_id']}: {verdict['verdict']}")


@app.command(name="gate")
def gate_cmd(
    study_yaml: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
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
    minimum = _validated_min_readiness(min_readiness)
    allowed_verdicts = _allowed_gate_verdicts(allow_verdict)
    root = _resolve_repo_root(repo_root)
    study = _load_study_or_exit(study_yaml)
    runs_frame = _resolve_runs_frame(study, root, runs)
    readiness = run_readiness(study_yaml, runs, study, runs_frame, repo_root=root)
    claims, failures = _gate_claims_and_failures(
        study=study,
        runs_frame=runs_frame,
        readiness=readiness,
        min_readiness=minimum,
        allowed_verdicts=allowed_verdicts,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )

    status = "pass" if not failures else "fail"
    payload: dict[str, object] = {
        "study_id": study.id,
        "status": status,
        "readiness": readiness.status,
        "allowed_verdicts": allowed_verdicts,
        "claims": claims,
        "failures": failures,
    }

    _emit_gate_output(payload, json_output=json_output)

    if failures:
        raise typer.Exit(code=1)


@app.command(name="portfolio")
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
            "WARNING: synthetic validation skipped (--skip-validation). "
            "The report contract requires this gate to pass before any report render. "
            "This run is for development/debug only; do NOT publish the resulting report."
        )
    else:
        gate_ok = _run_synthetic_validation_gate(root)
        if not gate_ok:
            typer.echo("synthetic-validation gate FAILED; refusing to write report.", err=True)
            raise typer.Exit(code=1)

    runs_frame = _resolve_runs_frame(study, root, runs)
    readiness = check_evidence(study, runs_frame, repo_root=root)
    if readiness.status == "not_ready":
        failed = [
            check.id
            for check in readiness.checks
            if check.severity == "error" and check.status == "fail"
        ]
        runs_arg = runs if runs is not None else _fixture_source(study, root).parquet_path
        check_out_path = out_dir / study.id / "check.json"
        typer.echo(
            "evidence readiness check FAILED; refusing to write report "
            f"(failed gates: {', '.join(failed)})\n"
            "For the full readiness JSON, run:\n"
            f"  eval-audit check {study_yaml} --runs {runs_arg} --out {check_out_path}",
            err=True,
        )
        raise typer.Exit(code=1)

    target_dir = out_dir / study.id
    target_dir.mkdir(parents=True, exist_ok=True)
    check_json = readiness.to_json_bytes()
    check_path = target_dir / "check.json"
    check_path.write_bytes(check_json)
    check_sha256 = hashlib.sha256(check_json).hexdigest()
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
        evidence_readiness=readiness.status,
        check_sha256=check_sha256,
    )
    typer.echo(f"wrote {check_path}")
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


@app.command(name="check")
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
