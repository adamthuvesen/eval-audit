"""Application workflow from validated evidence to prepared audit artifacts."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from eval_audit.checks import ReadinessCheck, ReadinessResult, check_prepared_evidence
from eval_audit.evidence import prepare_evidence
from eval_audit.report.decisions import decision_impact
from eval_audit.report.html import render_html_report
from eval_audit.report.markdown import render_report
from eval_audit.report.presentation import resolve_study_presentation
from eval_audit.report.provenance import EvidenceSource
from eval_audit.report.sensitivity import claim_context_for_result
from eval_audit.report.summary import build_audit_summary, summary_json_bytes
from eval_audit.schema import StudySpec
from eval_audit.schema.artifacts import ARTIFACT_FILES
from eval_audit.stats import AnalysisResult
from eval_audit.stats.analyze import analyze_prepared
from eval_audit.stats.results import AnalysisSettings


@dataclass(frozen=True)
class AuditProducts:
    result: AnalysisResult
    readiness: ReadinessResult
    artifacts: dict[str, bytes]


def serialise_result(result: AnalysisResult) -> dict:
    out = dataclasses.asdict(result)
    out["pareto_frontier"] = sorted(result.pareto_frontier)
    out["bootstrap_seed"] = result.bootstrap_seed
    return out


def analysis_json_bytes(result: AnalysisResult) -> bytes:
    return (json.dumps(serialise_result(result), allow_nan=False, indent=2) + "\n").encode()


def claim_verdicts(result: AnalysisResult, study: StudySpec) -> list[dict[str, str]]:
    return [
        {
            "claim_id": claim.claim_id,
            "verdict": decision_impact(claim_context_for_result(claim, result, study)),
        }
        for claim in result.claims
    ]


def build_audit(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    study_path: Path,
    source: EvidenceSource,
    repo_root: Path,
    bootstrap_iterations: int,
    bootstrap_seed: int,
    git_commit: str,
    html: bool = False,
) -> AuditProducts:
    """Complete validation, inference, and rendering before any output is written."""
    evidence = prepare_evidence(study, runs)
    study, runs = evidence.study, evidence.runs
    initial_checks = [
        ReadinessCheck(
            "study_loads", "error", "pass", "study YAML loaded", {"path": str(study_path)}, None
        ),
        ReadinessCheck(
            "runs_load",
            "error",
            "pass",
            "runs parquet loaded",
            {"path": source.display_path(repo_root), "rows": runs.height},
            None,
        ),
    ]
    readiness = check_prepared_evidence(
        evidence, repo_root=repo_root, initial_checks=initial_checks, source=source
    )
    result = analyze_prepared(
        evidence,
        settings=AnalysisSettings(
            alpha=study.inference.alpha,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        ),
    )
    check_bytes = readiness.to_json_bytes()
    markdown = render_report(
        result,
        study,
        runs,
        clock=lambda: datetime(1970, 1, 1, tzinfo=UTC),
        git_commit=git_commit,
        fixture_sha256=source.fixture_sha256,
        repo_root=repo_root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
        evidence_readiness=readiness.status,
        check_sha256=hashlib.sha256(check_bytes).hexdigest(),
        source=source,
    )
    artifacts = {
        "check.json": check_bytes,
        "analysis.json": analysis_json_bytes(result),
        "report.md": markdown.encode(),
    }
    if html:
        artifacts["report.html"] = render_html_report(
            markdown, title=f"{study.id} audit report"
        ).encode()
    presentation = resolve_study_presentation(study, runs, result, repo_root, source)
    summary = build_audit_summary(
        result=result,
        study=study,
        runs=runs,
        presentation=presentation,
        readiness=readiness.status,
        artifact_paths={
            key: Path(name) for key, name in ARTIFACT_FILES.items() if name in artifacts
        },
        artifact_bytes={
            key: artifacts[name] for key, name in ARTIFACT_FILES.items() if name in artifacts
        },
    )
    artifacts["summary.json"] = summary_json_bytes(summary)
    return AuditProducts(result, readiness, artifacts)
