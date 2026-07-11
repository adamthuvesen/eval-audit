"""Robustness review section rendering."""

from __future__ import annotations

from eval_audit.report import ReportContractError
from eval_audit.report.presentation import StudyPresentation
from eval_audit.report.sensitivity import SensitivityRow
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats.results import AnalysisResult

ROBUSTNESS_DIMENSIONS: tuple[str, ...] = (
    "Multiple-comparison correction",
    "Errored-row policy",
    "Cost-threshold sensitivity",
    "Target MDE",
    "Cost provenance",
)


def robustness_multiple_comparison(rows: list[SensitivityRow], baseline: str) -> tuple[str, str]:
    flipped: list[str] = []
    for r in rows:
        if r.dimension == "alpha" and r.value == "0.01" and r.verdict != baseline:
            flipped.append("α=0.01")
        elif r.dimension == "alpha" and r.value == "0.10" and r.verdict != baseline:
            flipped.append("α=0.10")
        elif r.dimension == "correction_method" and r.value == "none" and r.verdict != baseline:
            flipped.append("correction=none")
    if not flipped:
        return (
            "survives",
            "verdict unchanged at α∈{0.01, 0.10} and with correction=none",
        )
    return ("does not survive", f"verdict flips at {', '.join(flipped)}")


def robustness_errored_policy(rows: list[SensitivityRow], baseline: str) -> tuple[str, str]:
    for r in rows:
        if r.dimension == "errored_policy" and r.value == "excluded":
            if r.verdict == baseline:
                return ("survives", "verdict unchanged when errored rows excluded")
            return (
                "does not survive",
                f"verdict flips when errored rows excluded ({baseline} → {r.verdict})",
            )
    raise ReportContractError("errored_policy=excluded row missing from sensitivity rows")


def robustness_cost_threshold(
    rows: list[SensitivityRow], baseline: str, *, pareto_suppressed: bool = False
) -> tuple[str, str]:
    if pareto_suppressed:
        return (
            "n/a",
            "cost-gap threshold not applicable; cost provenance is "
            f"{CostProvenance.COST_NOT_AVAILABLE.value}",
        )
    flipped: list[str] = []
    for r in rows:
        if r.dimension == "cost_gap_threshold" and r.verdict != baseline:
            flipped.append(r.value)
    if not flipped:
        return (
            "survives",
            "verdict unchanged at cost_gap_threshold∈{0.05, 0.20}",
        )
    return (
        "does not survive",
        f"verdict flips at cost_gap_threshold={', '.join(flipped)}",
    )


def robustness_target_mde(target_mde: float | None, ci_half_width: float) -> tuple[str, str]:
    if target_mde is None:
        return ("not assessed", "inference.target_mde not declared")
    half_pp = ci_half_width * 100
    mde_pp = target_mde * 100
    if ci_half_width <= target_mde:
        return (
            "survives",
            f"CI half-width {half_pp:.2f} pp ≤ MDE {mde_pp:.2f} pp; sufficiently resolved",
        )
    return (
        "does not survive",
        f"CI half-width {half_pp:.2f} pp > MDE {mde_pp:.2f} pp; under-resolved",
    )


def robustness_cost_provenance(cost_provenance: str) -> tuple[str, str]:
    if cost_provenance == CostProvenance.RECONCILED.value:
        return ("survives", "reconciled")
    if cost_provenance in (CostProvenance.AS_REPORTED_ONLY.value, "partial"):
        return ("caveat", cost_provenance)
    if cost_provenance == CostProvenance.COST_NOT_AVAILABLE.value:
        return (
            "does not survive",
            "cost_not_available — Pareto and cost-per-success suppressed; "
            "see Cost provenance caveat",
        )
    return ("does not survive", cost_provenance)


def render_robustness_review_table(
    rows: list[SensitivityRow],
    baseline: str,
    target_mde: float | None,
    ci_half_width: float,
    presentation: StudyPresentation,
) -> list[str]:
    parts = ["| Dimension | Result | Notes |", "|---|---|---|"]
    result, notes = robustness_multiple_comparison(rows, baseline)
    parts.append(f"| Multiple-comparison correction | {result} | {notes} |")
    result, notes = robustness_errored_policy(rows, baseline)
    parts.append(f"| Errored-row policy | {result} | {notes} |")
    result, notes = robustness_cost_threshold(
        rows, baseline, pareto_suppressed=presentation.pareto_suppressed
    )
    parts.append(f"| Cost-threshold sensitivity | {result} | {notes} |")
    result, notes = robustness_target_mde(target_mde, ci_half_width)
    parts.append(f"| Target MDE | {result} | {notes} |")
    result, notes = robustness_cost_provenance(presentation.cost_provenance)
    parts.append(f"| Cost provenance | {result} | {notes} |")
    return parts


def render_robustness_review(
    result: AnalysisResult,
    study: StudySpec,
    sensitivity_rows_by_claim: dict[str, list[SensitivityRow]],
    presentation: StudyPresentation,
) -> list[str]:
    parts: list[str] = ["## Robustness Review\n"]
    target_mde = study.inference.target_mde
    multi_claim = len(result.claims) > 1
    for c in result.claims:
        rows = sensitivity_rows_by_claim[c.claim_id]
        baseline = rows[0].verdict
        ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0
        if multi_claim:
            parts.append(f"### Claim `{c.claim_id}`\n")
        parts.extend(
            render_robustness_review_table(rows, baseline, target_mde, ci_half_width, presentation)
        )
        parts.append("")
    return parts
