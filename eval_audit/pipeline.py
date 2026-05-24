"""Shared audit pipeline helpers for CLI commands."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from eval_audit.checks import ReadinessResult, check_loaded_evidence
from eval_audit.report.decisions import decision_impact
from eval_audit.report.markdown import render_report
from eval_audit.report.presentation import resolve_study_presentation
from eval_audit.report.sensitivity import claim_context_for_result
from eval_audit.report.summary import build_audit_summary, summary_json_bytes
from eval_audit.schema import StudySpec
from eval_audit.stats import AnalysisResult, analyze

_DETERMINISTIC_AUDIT_CLOCK = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class AuditArtifacts:
    readiness: ReadinessResult
    result: AnalysisResult
    check_path: Path
    analysis_path: Path
    report_path: Path
    summary_path: Path
    html_path: Path | None = None


def serialise_result(result: AnalysisResult) -> dict:
    out = dataclasses.asdict(result)
    if isinstance(out.get("pareto_frontier"), set):
        out["pareto_frontier"] = sorted(out["pareto_frontier"])
    return out


def analysis_json_bytes(result: AnalysisResult) -> bytes:
    return (
        json.dumps(serialise_result(result), allow_nan=False, indent=2, default=str) + "\n"
    ).encode()


def write_analysis_json(result: AnalysisResult, target_dir: Path) -> Path:
    target = target_dir / "analysis.json"
    target.write_bytes(analysis_json_bytes(result))
    return target


def write_check_json(readiness: ReadinessResult, target_dir: Path) -> tuple[Path, str]:
    check_json = readiness.to_json_bytes()
    check_path = target_dir / "check.json"
    check_path.write_bytes(check_json)
    return check_path, hashlib.sha256(check_json).hexdigest()


def run_analysis(
    study: StudySpec,
    runs_frame: pl.DataFrame,
    *,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> AnalysisResult:
    return analyze(
        study,
        runs_frame,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )


def run_readiness(
    study_yaml: Path,
    runs_path: Path,
    study: StudySpec,
    runs_frame: pl.DataFrame,
    *,
    repo_root: Path,
) -> ReadinessResult:
    return check_loaded_evidence(
        study_yaml,
        runs_path,
        study,
        runs_frame,
        repo_root=repo_root,
    )


def render_audit_markdown(
    result: AnalysisResult,
    study: StudySpec,
    runs_frame: pl.DataFrame,
    *,
    repo_root: Path,
    runs_path: Path | None,
    readiness: ReadinessResult,
    check_sha256: str,
    bootstrap_iterations: int,
    bootstrap_seed: int,
    git_commit: str,
    fixture_sha256: str,
    deterministic_clock: bool = False,
) -> str:
    clock: Callable[[], datetime] = (
        (lambda: _DETERMINISTIC_AUDIT_CLOCK) if deterministic_clock else (lambda: datetime.now(UTC))
    )
    return render_report(
        result,
        study,
        runs_frame,
        clock=clock,
        git_commit=git_commit,
        fixture_sha256=fixture_sha256,
        repo_root=repo_root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
        evidence_readiness=readiness.status,
        check_sha256=check_sha256,
    )


def claim_verdicts(result: AnalysisResult, study: StudySpec) -> list[dict[str, str]]:
    verdicts: list[dict[str, str]] = []
    for claim in result.claims:
        ctx = claim_context_for_result(claim, result, study)
        verdicts.append(
            {
                "claim_id": claim.claim_id,
                "verdict": decision_impact(ctx),
            }
        )
    return verdicts


def write_summary_json(
    *,
    result: AnalysisResult,
    study: StudySpec,
    runs_frame: pl.DataFrame,
    readiness: ReadinessResult,
    repo_root: Path,
    target_dir: Path,
    check_path: Path,
    analysis_path: Path,
    report_path: Path,
    html_path: Path | None,
) -> Path:
    presentation = resolve_study_presentation(study, runs_frame, result, repo_root)
    artifact_paths = {
        "check_json": check_path,
        "analysis_json": analysis_path,
        "report_md": report_path,
    }
    if html_path is not None:
        artifact_paths["report_html"] = html_path
    payload = build_audit_summary(
        result=result,
        study=study,
        runs=runs_frame,
        presentation=presentation,
        readiness=readiness.status,
        artifact_paths=artifact_paths,
    )
    target = target_dir / "summary.json"
    target.write_bytes(summary_json_bytes(payload))
    return target
