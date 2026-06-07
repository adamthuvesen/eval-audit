"""Acceptance tests for the decision_impact rule table."""

from __future__ import annotations


def _stub_claim_result(
    *,
    rejects: bool = False,
    delta_lo: float = -0.05,
    delta_hi: float = 0.05,
    delta_point: float = 0.0,
    treatment_cost: float = 100.0,
    control_cost: float = 100.0,
    treatment_dominated: bool = False,
    direction_matches_claim: bool = True,
):
    from eval_audit.report.decisions import ClaimContext

    return ClaimContext(
        rejects_null=rejects,
        delta_point_estimate=delta_point,
        delta_ci_low=delta_lo,
        delta_ci_high=delta_hi,
        treatment_cost_usd=treatment_cost,
        control_cost_usd=control_cost,
        treatment_is_dominated=treatment_dominated,
        direction_matches_claim=direction_matches_claim,
    )


def test_decision_impact__inconclusive_with_cost_gap_maps_to_hedge_on_cost() -> None:
    """WHEN the GAIA HAL Generalist reanalysis produces a delta CI that crosses zero and
    Claude is 2.2x more expensive than o4-mini,
    THEN the report's claim row has decision_impact == 'hedge_on_cost'.
    """
    from eval_audit.report.decisions import decision_impact

    ctx = _stub_claim_result(
        rejects=False,
        delta_lo=-0.05,
        delta_hi=0.07,
        delta_point=0.019,
        treatment_cost=130.68,
        control_cost=59.39,
        treatment_dominated=False,
    )
    assert decision_impact(ctx) == "hedge_on_cost"


def test_decision_impact__rejects_table_branches() -> None:
    """Each branch of the rule table maps to its declared label."""
    from eval_audit.report.decisions import decision_impact

    # Pareto-dominated treatment -> drop_from_shortlist (highest priority).
    assert (
        decision_impact(_stub_claim_result(treatment_dominated=True, rejects=True))
        == "drop_from_shortlist"
    )

    # Rejects + matching direction -> switch.
    assert (
        decision_impact(
            _stub_claim_result(
                rejects=True,
                delta_point=0.05,
                delta_lo=0.01,
                delta_hi=0.09,
                direction_matches_claim=True,
            )
        )
        == "switch"
    )

    # Rejects + opposite direction -> hold.
    assert (
        decision_impact(
            _stub_claim_result(
                rejects=True,
                delta_point=-0.05,
                delta_lo=-0.09,
                delta_hi=-0.01,
                direction_matches_claim=False,
            )
        )
        == "hold"
    )

    # CI crosses zero, no meaningful cost gap -> rerun_more_n.
    assert (
        decision_impact(
            _stub_claim_result(
                rejects=False, delta_lo=-0.02, delta_hi=0.02, treatment_cost=100, control_cost=101
            )
        )
        == "rerun_more_n"
    )

    # CI crosses zero, large cost gap -> hedge_on_cost.
    assert (
        decision_impact(
            _stub_claim_result(
                rejects=False, delta_lo=-0.02, delta_hi=0.02, treatment_cost=200, control_cost=100
            )
        )
        == "hedge_on_cost"
    )


def test_explain_decision_impact__covers_controlled_branches() -> None:
    from eval_audit.report.decisions import explain_decision_impact

    cases = [
        (
            _stub_claim_result(treatment_dominated=True, rejects=True),
            "drop_from_shortlist",
            "pareto_domination",
        ),
        (
            _stub_claim_result(
                rejects=True,
                delta_point=0.05,
                delta_lo=0.01,
                delta_hi=0.09,
                direction_matches_claim=True,
            ),
            "switch",
            "rejecting_adjusted_p_value_claim_direction",
        ),
        (
            _stub_claim_result(
                rejects=True,
                delta_point=-0.05,
                delta_lo=-0.09,
                delta_hi=-0.01,
                direction_matches_claim=False,
            ),
            "hold",
            "rejecting_adjusted_p_value_opposite_direction",
        ),
        (
            _stub_claim_result(
                rejects=False,
                delta_lo=-0.02,
                delta_hi=0.02,
                treatment_cost=200,
                control_cost=100,
            ),
            "hedge_on_cost",
            "uncertainty_with_material_cost_gap",
        ),
        (
            _stub_claim_result(
                rejects=False,
                delta_lo=-0.02,
                delta_hi=0.02,
                treatment_cost=101,
                control_cost=100,
            ),
            "rerun_more_n",
            "uncertainty_without_material_cost_gap",
        ),
        (
            _stub_claim_result(
                rejects=False,
                delta_lo=0.01,
                delta_hi=0.08,
                treatment_cost=101,
                control_cost=100,
            ),
            "inconclusive_no_action",
            "fallback_inconclusive",
        ),
    ]

    for ctx, verdict, branch in cases:
        explanation = explain_decision_impact(ctx)
        assert explanation.verdict == verdict
        assert explanation.first_matching_branch == branch


def test_explain_decision_impact__cost_not_available_suppresses_cost_branch() -> None:
    from eval_audit.report.decisions import explain_decision_impact

    explanation = explain_decision_impact(
        _stub_claim_result(
            rejects=False,
            delta_lo=-0.02,
            delta_hi=0.02,
            treatment_cost=None,
            control_cost=None,
        )
    )

    assert explanation.verdict == "rerun_more_n"
    assert explanation.conditions["cost_available"] is False
    assert explanation.suppressed_branches == ["uncertainty_with_material_cost_gap"]
    assert "cost" in explanation.summary


def test_decision_impact__cost_gap_threshold_kwarg_perturbs_verdict() -> None:
    """WHEN a claim has a 7% cost gap and a CI crossing zero,
    THEN the verdict resolves to rerun_more_n under the default 0.10 threshold
    AND to hedge_on_cost under a perturbed 0.05 threshold.
    """
    from eval_audit.report.decisions import decision_impact

    ctx = _stub_claim_result(
        rejects=False,
        delta_lo=-0.02,
        delta_hi=0.02,
        treatment_cost=107.0,
        control_cost=100.0,
    )

    # Default threshold (0.10): 7% gap is not meaningful -> rerun_more_n.
    assert decision_impact(ctx) == "rerun_more_n"

    # Perturbed threshold (0.05): 7% gap is now meaningful -> hedge_on_cost.
    assert decision_impact(ctx, cost_gap_threshold=0.05) == "hedge_on_cost"

    # Perturbed threshold (0.20): 7% gap still not meaningful -> rerun_more_n.
    assert decision_impact(ctx, cost_gap_threshold=0.20) == "rerun_more_n"


def test_decision_impact__unknown_values_are_forbidden() -> None:
    """WHEN the renderer is asked to emit a claim row whose computed decision_impact
    is not in the controlled vocabulary, THEN ReportContractError is raised.
    """
    import pytest

    from eval_audit.report import ReportContractError
    from eval_audit.report.markdown import render_claim_row

    # Forge an analysis result with a bogus decision_impact and confirm rendering rejects it.
    bad_row = {
        "claim_id": "x",
        "mode": "declared_reanalysis",
        "status": "inconclusive",
        "effect": "+1.0 pp",
        "adjusted_result": "n/a",
        "decision_impact": "totally_made_up",
    }
    with pytest.raises(ReportContractError):
        render_claim_row(bad_row)
