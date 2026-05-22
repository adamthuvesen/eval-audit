"""Deterministic structured claim summaries for completed audit artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import polars as pl

from eval_audit.report.decisions import explain_decision_impact
from eval_audit.report.sensitivity import claim_context_for_result
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats import AnalysisResult


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dominant_cost_provenance(runs: pl.DataFrame) -> str:
    if "cost_provenance" not in runs.columns or runs.is_empty():
        return "n/a"
    counts = runs.group_by("cost_provenance").len().sort("len", descending=True)
    if counts.is_empty():
        return "n/a"
    return str(counts.row(0)[0])


def claim_status(rejects: bool, direction_matches: bool) -> str:
    if rejects and direction_matches:
        return "supported"
    if rejects and not direction_matches:
        return "unsupported"
    return "inconclusive"


def paired_task_count(runs: pl.DataFrame, treatment: str, control: str) -> int:
    treatment_tasks = runs.filter(pl.col("agent_id") == treatment).select("task_id").unique()
    control_tasks = runs.filter(pl.col("agent_id") == control).select("task_id").unique()
    return treatment_tasks.join(control_tasks, on="task_id", how="inner").height


def cost_caveat(
    *,
    cost_provenance: str,
    treatment_cost: float | None,
    control_cost: float | None,
) -> str:
    if cost_provenance == CostProvenance.COST_NOT_AVAILABLE.value:
        return (
            "cost provenance is cost_not_available; cost-derived views and "
            "cost-driven verdict branches are suppressed"
        )
    if cost_provenance == CostProvenance.AS_REPORTED_ONLY.value:
        return (
            "cost provenance is as_reported_only; costs come from reported totals "
            "rather than reconciled per-task reconstruction"
        )
    if treatment_cost is None or control_cost is None:
        return "no reliable cost ratio is available"
    if control_cost > 0:
        return f"treatment cost is {treatment_cost / control_cost:.2f}x control"
    return "control cost is zero, so the cost ratio is undefined"


def human_claim_summary(
    *,
    claim_id: str,
    treatment: str,
    control: str,
    verdict: str,
    readiness: str,
    delta: float,
    ci_low: float,
    ci_high: float,
    caveat: str,
) -> str:
    return (
        f"Claim `{claim_id}` verdict `{verdict}` for `{treatment}` vs `{control}`: "
        f"delta {delta * 100:+.2f} pp with bootstrap CI "
        f"[{ci_low * 100:+.2f} pp, {ci_high * 100:+.2f} pp]; "
        f"evidence readiness `{readiness}`. Cost caveat: {caveat}."
    )


def build_audit_summary(
    *,
    result: AnalysisResult,
    study: StudySpec,
    runs: pl.DataFrame,
    readiness: str,
    artifact_paths: dict[str, Path],
) -> dict[str, Any]:
    """Build the stable summary.json payload for one completed audit."""
    cost_provenance = dominant_cost_provenance(runs)
    artifact_hashes = {
        name: file_sha256(path)
        for name, path in artifact_paths.items()
        if path.exists() and name in {"check_json", "analysis_json", "report_md"}
    }
    artifact_path_values = {name: path.name for name, path in artifact_paths.items()}

    claims: list[dict[str, Any]] = []
    for claim in result.claims:
        ctx = claim_context_for_result(claim, result, study)
        explanation = explain_decision_impact(ctx)
        status = claim_status(claim.rejects_null, ctx.direction_matches_claim)
        caveat = cost_caveat(
            cost_provenance=cost_provenance,
            treatment_cost=ctx.treatment_cost_usd,
            control_cost=ctx.control_cost_usd,
        )
        claims.append(
            {
                "study_id": study.id,
                "claim_id": claim.claim_id,
                "claim_text": claim.text,
                "treatment": claim.treatment,
                "control": claim.control,
                "verdict": explanation.verdict,
                "claim_status": status,
                "readiness": readiness,
                "delta": claim.delta_point_estimate,
                "ci_low": claim.delta_ci_low,
                "ci_high": claim.delta_ci_high,
                "adjusted_p_value": claim.adjusted_p_value,
                "rejects_null": claim.rejects_null,
                "paired_tasks": paired_task_count(runs, claim.treatment, claim.control),
                "cost_provenance": cost_provenance,
                "treatment_total_cost_usd": ctx.treatment_cost_usd,
                "control_total_cost_usd": ctx.control_cost_usd,
                "cost_caveat": caveat,
                "verdict_explanation": {
                    "verdict": explanation.verdict,
                    "first_matching_branch": explanation.first_matching_branch,
                    "conditions": explanation.conditions,
                    "suppressed_branches": explanation.suppressed_branches,
                    "summary": explanation.summary,
                },
                "human_summary": human_claim_summary(
                    claim_id=claim.claim_id,
                    treatment=claim.treatment,
                    control=claim.control,
                    verdict=explanation.verdict,
                    readiness=readiness,
                    delta=claim.delta_point_estimate,
                    ci_low=claim.delta_ci_low,
                    ci_high=claim.delta_ci_high,
                    caveat=caveat,
                ),
                "artifact_paths": artifact_path_values,
                "artifact_hashes": artifact_hashes,
            }
        )

    return {
        "schema_version": 1,
        "study_id": study.id,
        "readiness": readiness,
        "artifact_paths": artifact_path_values,
        "artifact_hashes": artifact_hashes,
        "claims": claims,
    }


def summary_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True, default=str) + "\n"
    ).encode()
