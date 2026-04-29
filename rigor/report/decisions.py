"""Controlled-vocabulary decision_impact rule table for claim rows."""

from __future__ import annotations

from dataclasses import dataclass

DECISION_IMPACT_VOCAB: tuple[str, ...] = (
    "switch",
    "hold",
    "drop_from_shortlist",
    "rerun_more_n",
    "hedge_on_cost",
    "inconclusive_no_action",
)

# Cost gap is "meaningful" when treatment cost differs from the cheaper arm by >=10%.
COST_GAP_THRESHOLD = 0.10


@dataclass(frozen=True)
class ClaimContext:
    rejects_null: bool
    delta_point_estimate: float
    delta_ci_low: float
    delta_ci_high: float
    treatment_cost_usd: float
    control_cost_usd: float
    treatment_is_dominated: bool
    direction_matches_claim: bool


def decision_impact(
    ctx: ClaimContext,
    *,
    cost_gap_threshold: float = COST_GAP_THRESHOLD,
) -> str:
    """Map an analysis result to a controlled decision_impact label.

    Rule order is significant: first match wins. The `cost_gap_threshold`
    kwarg is exposed so the verdict-sensitivity table can perturb it; the
    default reproduces the v0 behavior.
    """
    if ctx.treatment_is_dominated:
        return "drop_from_shortlist"
    if ctx.rejects_null and ctx.direction_matches_claim:
        return "switch"
    if ctx.rejects_null and not ctx.direction_matches_claim:
        return "hold"
    ci_crosses_zero = ctx.delta_ci_low <= 0.0 <= ctx.delta_ci_high
    if ci_crosses_zero:
        cheaper = min(ctx.treatment_cost_usd, ctx.control_cost_usd)
        gap = abs(ctx.treatment_cost_usd - ctx.control_cost_usd)
        meaningful_gap = cheaper > 0 and (gap / cheaper) >= cost_gap_threshold
        return "hedge_on_cost" if meaningful_gap else "rerun_more_n"
    return "inconclusive_no_action"
