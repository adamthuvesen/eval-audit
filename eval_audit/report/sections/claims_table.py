"""Claims table, verdict explainers, and MDE context."""

from __future__ import annotations

from eval_audit.report import ReportContractError
from eval_audit.report.decisions import DECISION_IMPACT_VOCAB, explain_decision_impact
from eval_audit.report.presentation import StudyPresentation
from eval_audit.report.vocabulary import STATUS_VOCAB
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats.results import ClaimResult


def copyable_claim_summary(
    *,
    claim_id: str,
    treatment: str,
    control: str,
    verdict: str,
    readiness: str,
    delta: float,
    ci_low: float,
    ci_high: float,
    presentation: StudyPresentation,
    treatment_cost: float | None,
    control_cost: float | None,
) -> str:
    delta_pp = delta * 100
    ci_low_pp = ci_low * 100
    ci_high_pp = ci_high * 100
    if presentation.cost_provenance == CostProvenance.COST_NOT_AVAILABLE.value:
        caveat = (
            " Cost caveat: cost provenance is cost_not_available, so cost-derived "
            "views and cost-driven verdict branches are suppressed."
        )
    elif presentation.cost_provenance == CostProvenance.AS_REPORTED_ONLY.value:
        caveat = (
            " Cost caveat: cost provenance is as_reported_only, so costs come "
            "from reported totals rather than reconciled per-task reconstruction."
        )
    elif treatment_cost is None or control_cost is None:
        caveat = " Cost caveat: no reliable cost ratio is available."
    elif control_cost > 0:
        caveat = f" Cost note: treatment cost is {treatment_cost / control_cost:.2f}x control."
    else:
        caveat = " Cost note: control cost is zero, so the cost ratio is undefined."

    return (
        f"Claim `{claim_id}` verdict `{verdict}` for `{treatment}` vs `{control}`: "
        f"delta {delta_pp:+.2f} pp with bootstrap CI "
        f"[{ci_low_pp:+.2f} pp, {ci_high_pp:+.2f} pp]; "
        f"evidence readiness `{readiness}`.{caveat}"
    )


def render_verdict_explainer(
    *,
    claim: ClaimResult,
    presentation: StudyPresentation,
    evidence_readiness: str,
    ctx,
) -> list[str]:
    explanation = explain_decision_impact(ctx)
    cost_gap_ratio = explanation.conditions["cost_gap_ratio"]
    cost_gap_text = "n/a" if cost_gap_ratio is None else f"{cost_gap_ratio:.2%}"
    suppressed = (
        ", ".join(explanation.suppressed_branches)
        if explanation.suppressed_branches
        else "none"
    )
    parts = [
        f"**Copyable summary** — `{claim.claim_id}`\n",
        copyable_claim_summary(
            claim_id=claim.claim_id,
            treatment=claim.treatment,
            control=claim.control,
            verdict=explanation.verdict,
            readiness=evidence_readiness,
            delta=claim.delta_point_estimate,
            ci_low=claim.delta_ci_low,
            ci_high=claim.delta_ci_high,
            presentation=presentation,
            treatment_cost=ctx.treatment_cost_usd,
            control_cost=ctx.control_cost_usd,
        ),
        "",
        f"**Verdict explainer** — `{claim.claim_id}`\n",
        f"- **First matching branch:** `{explanation.first_matching_branch}` → `{explanation.verdict}`",
        f"- **Rule path:** {explanation.summary}",
        (
            "- **Evaluated conditions:** "
            f"Pareto dominated={ctx.treatment_is_dominated}; "
            f"adjusted-p rejection={ctx.rejects_null}; "
            f"effect direction matches claim={ctx.direction_matches_claim}; "
            f"quality CI crosses zero={explanation.conditions['ci_crosses_zero']}; "
            f"cost gap ratio={cost_gap_text}; "
            f"material cost-gap threshold={explanation.conditions['cost_gap_threshold']:.0%}."
        ),
        f"- **Suppressed branches:** {suppressed}.",
        "",
    ]
    return parts


def render_claim_row(row: dict) -> str:
    """Render a single claim row, validating its decision_impact value.

    Raises ReportContractError if the row's decision_impact is not in the controlled vocabulary.
    The target_mde column is included only when row['target_mde'] is set.
    """
    di = row.get("decision_impact")
    if di not in DECISION_IMPACT_VOCAB:
        raise ReportContractError(
            f"decision_impact={di!r} is not in controlled vocabulary {DECISION_IMPACT_VOCAB}"
        )
    status = row.get("status")
    if status not in STATUS_VOCAB:
        raise ReportContractError(
            f"status={status!r} is not in controlled vocabulary {sorted(STATUS_VOCAB)}"
        )
    if "target_mde" in row:
        return (
            f"| {row['claim_id']} | {row['mode']} | {row['status']} | "
            f"{row['effect']} | {row['target_mde']} | "
            f"{row['adjusted_result']} | {row['decision_impact']} |"
        )
    return (
        f"| {row['claim_id']} | {row['mode']} | {row['status']} | "
        f"{row['effect']} | {row['adjusted_result']} | {row['decision_impact']} |"
    )
