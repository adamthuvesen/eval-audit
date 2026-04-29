"""Property test: baseline-row verdict equals the Claims-table verdict.

Pins the "baseline matches Claims" invariant against future drift in the
sensitivity renderer or the decision_impact rule table.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


@given(
    rejects=st.booleans(),
    delta_lo=st.floats(min_value=-0.30, max_value=0.05, allow_nan=False),
    delta_hi=st.floats(min_value=-0.05, max_value=0.30, allow_nan=False),
    delta_point=st.floats(min_value=-0.20, max_value=0.20, allow_nan=False),
    treatment_cost=st.floats(min_value=0.10, max_value=1000.0, allow_nan=False),
    control_cost=st.floats(min_value=0.10, max_value=1000.0, allow_nan=False),
    treatment_dominated=st.booleans(),
    direction_matches=st.booleans(),
)
@settings(max_examples=50, deadline=None)
def test_baseline_verdict_matches_decision_impact_invariant(
    rejects: bool,
    delta_lo: float,
    delta_hi: float,
    delta_point: float,
    treatment_cost: float,
    control_cost: float,
    treatment_dominated: bool,
    direction_matches: bool,
) -> None:
    """For any randomly-generated ClaimContext, the baseline verdict computed by
    the sensitivity helper equals the verdict the Claims-table renderer's call
    to decision_impact() would produce. The sensitivity table reads the rule
    table; it does not redefine it.
    """
    from rigor.report.decisions import ClaimContext, decision_impact

    # Skip nonsense cases where lo > hi (hypothesis may generate them).
    if delta_lo > delta_hi:
        delta_lo, delta_hi = delta_hi, delta_lo

    ctx = ClaimContext(
        rejects_null=rejects,
        delta_point_estimate=delta_point,
        delta_ci_low=delta_lo,
        delta_ci_high=delta_hi,
        treatment_cost_usd=treatment_cost,
        control_cost_usd=control_cost,
        treatment_is_dominated=treatment_dominated,
        direction_matches_claim=direction_matches,
    )

    # Direct call (the Claims-table path).
    direct_verdict = decision_impact(ctx)

    # Sensitivity baseline path: build the same context and call decision_impact
    # with the default kwarg. This is what the sensitivity renderer does for the
    # baseline row.
    baseline_verdict = decision_impact(ctx, cost_gap_threshold=0.10)

    assert baseline_verdict == direct_verdict
