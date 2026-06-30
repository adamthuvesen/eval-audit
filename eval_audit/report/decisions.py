"""Controlled-vocabulary decision_impact rule table for claim rows."""

from __future__ import annotations

from dataclasses import dataclass


def _pair_costs(ctx: ClaimContext) -> tuple[float, float]:
    assert ctx.treatment_cost_usd is not None and ctx.control_cost_usd is not None
    return ctx.treatment_cost_usd, ctx.control_cost_usd


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
    treatment_cost_usd: float | None
    control_cost_usd: float | None
    treatment_is_dominated: bool
    direction_matches_claim: bool


@dataclass(frozen=True)
class VerdictExplanation:
    verdict: str
    first_matching_branch: str
    conditions: dict[str, bool | float | None]
    suppressed_branches: list[str]
    summary: str


def _explanation(
    *,
    verdict: str,
    branch: str,
    conditions: dict[str, bool | float | None],
    suppressed_branches: list[str],
    summary: str,
) -> VerdictExplanation:
    return VerdictExplanation(
        verdict=verdict,
        first_matching_branch=branch,
        conditions=conditions,
        suppressed_branches=suppressed_branches,
        summary=summary,
    )


def _decision_conditions(
    ctx: ClaimContext,
    cost_gap_threshold: float,
) -> tuple[dict[str, bool | float | None], list[str]]:
    ci_crosses_zero = ctx.delta_ci_low <= 0.0 <= ctx.delta_ci_high
    cost_available = ctx.treatment_cost_usd is not None and ctx.control_cost_usd is not None
    cost_gap_ratio: float | None = None
    has_material_cost_gap = False
    suppressed_branches: list[str] = []

    if cost_available:
        treatment_cost, control_cost = _pair_costs(ctx)
        cheaper_cost = min(treatment_cost, control_cost)
        gap = abs(treatment_cost - control_cost)
        cost_gap_ratio = gap / cheaper_cost if cheaper_cost > 0 else None
        has_material_cost_gap = cost_gap_ratio is not None and cost_gap_ratio >= cost_gap_threshold
    elif ci_crosses_zero:
        suppressed_branches.append("uncertainty_with_material_cost_gap")

    return (
        {
            "treatment_is_dominated": ctx.treatment_is_dominated,
            "rejects_adjusted_null": ctx.rejects_null,
            "effect_direction_matches_claim": ctx.direction_matches_claim,
            "ci_crosses_zero": ci_crosses_zero,
            "cost_available": cost_available,
            "cost_gap_threshold": cost_gap_threshold,
            "cost_gap_ratio": cost_gap_ratio,
            "has_material_cost_gap": has_material_cost_gap,
        },
        suppressed_branches,
    )


def _uncertainty_explanation(
    ctx: ClaimContext,
    conditions: dict[str, bool | float | None],
    suppressed_branches: list[str],
) -> VerdictExplanation:
    # Cost suppression: if either arm has no honest cost, the cost-gap branch is
    # unreachable (hedge_on_cost cannot fire). Fall through to rerun_more_n —
    # collecting more paired tasks can still tighten the quality CI even when
    # cost data is permanently absent. This matches the "no meaningful cost gap"
    # branch for finite-cost studies.
    if ctx.treatment_cost_usd is None or ctx.control_cost_usd is None:
        return _explanation(
            verdict="rerun_more_n",
            branch="uncertainty_without_material_cost_gap",
            conditions=conditions,
            suppressed_branches=suppressed_branches,
            summary=(
                "The quality interval crosses zero; cost-dependent branches "
                "are suppressed because honest cost data is unavailable."
            ),
        )
    if conditions["has_material_cost_gap"] is True:
        return _explanation(
            verdict="hedge_on_cost",
            branch="uncertainty_with_material_cost_gap",
            conditions=conditions,
            suppressed_branches=suppressed_branches,
            summary=(
                "The quality interval crosses zero and the cost gap meets the material threshold."
            ),
        )
    return _explanation(
        verdict="rerun_more_n",
        branch="uncertainty_without_material_cost_gap",
        conditions=conditions,
        suppressed_branches=suppressed_branches,
        summary=(
            "The quality interval crosses zero and the cost gap is below the material threshold."
        ),
    )


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
    return explain_decision_impact(ctx, cost_gap_threshold=cost_gap_threshold).verdict


def explain_decision_impact(
    ctx: ClaimContext,
    *,
    cost_gap_threshold: float = COST_GAP_THRESHOLD,
) -> VerdictExplanation:
    """Return the first matching decision branch and the conditions it evaluated."""
    conditions, suppressed_branches = _decision_conditions(ctx, cost_gap_threshold)

    if ctx.treatment_is_dominated:
        return _explanation(
            verdict="drop_from_shortlist",
            branch="pareto_domination",
            conditions=conditions,
            suppressed_branches=suppressed_branches,
            summary=(
                "Treatment is Pareto-dominated before statistical or cost-gap "
                "branches are considered."
            ),
        )
    if ctx.rejects_null and ctx.direction_matches_claim:
        return _explanation(
            verdict="switch",
            branch="rejecting_adjusted_p_value_claim_direction",
            conditions=conditions,
            suppressed_branches=suppressed_branches,
            summary=(
                "The correction-adjusted p-value rejects the null and the effect "
                "direction matches the declared claim."
            ),
        )
    if ctx.rejects_null and not ctx.direction_matches_claim:
        return _explanation(
            verdict="hold",
            branch="rejecting_adjusted_p_value_opposite_direction",
            conditions=conditions,
            suppressed_branches=suppressed_branches,
            summary=(
                "The correction-adjusted p-value rejects the null, but the effect "
                "direction is opposite the declared claim."
            ),
        )
    if conditions["ci_crosses_zero"] is True:
        return _uncertainty_explanation(ctx, conditions, suppressed_branches)
    return _explanation(
        verdict="inconclusive_no_action",
        branch="fallback_inconclusive",
        conditions=conditions,
        suppressed_branches=suppressed_branches,
        summary=("No dominance, rejection, uncertainty-cost, or under-resolution branch matched."),
    )


def direction_matches_claim(direction: str, delta_point_estimate: float) -> bool:
    """Return whether treatment-control delta matches the declared outcome direction."""
    if direction == "higher_is_better":
        return delta_point_estimate >= 0
    if direction == "lower_is_better":
        return delta_point_estimate <= 0
    raise ValueError(f"unsupported primary_outcome.direction={direction!r}")
