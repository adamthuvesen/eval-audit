"""Decision-rule and rendering tests for cost_not_available studies."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

FIXED_CLOCK = datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC)


def _ctx(
    *,
    rejects: bool = False,
    delta_lo: float = -0.05,
    delta_hi: float = 0.05,
    delta_point: float = 0.0,
    treatment_cost: float | None = 100.0,
    control_cost: float | None = 100.0,
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


def test_decision_impact__ci_crosses_zero_with_null_costs_returns_rerun_more_n() -> None:
    """When CI crosses zero and either cost is None, the verdict is rerun_more_n.

    Cost suppression makes hedge_on_cost unreachable, but more paired tasks
    can still tighten the quality CI — the actionable signal must stay alive.
    """
    from eval_audit.report.decisions import decision_impact

    ctx = _ctx(
        rejects=False,
        delta_lo=-0.02,
        delta_hi=0.02,
        treatment_cost=None,
        control_cost=None,
    )

    assert decision_impact(ctx) == "rerun_more_n"


def test_decision_impact__ci_crosses_zero_with_one_null_cost_returns_rerun_more_n() -> None:
    """A single missing cost is enough to suppress the cost branch and fall to rerun_more_n."""
    from eval_audit.report.decisions import decision_impact

    ctx_left = _ctx(treatment_cost=None, control_cost=100.0)
    ctx_right = _ctx(treatment_cost=100.0, control_cost=None)

    assert decision_impact(ctx_left) == "rerun_more_n"
    assert decision_impact(ctx_right) == "rerun_more_n"


def test_decision_impact__finite_costs_meaningful_gap_still_returns_hedge_on_cost() -> None:
    """Regression: the existing finite-cost branch is unchanged for studies with cost."""
    from eval_audit.report.decisions import decision_impact

    ctx = _ctx(
        rejects=False,
        delta_lo=-0.02,
        delta_hi=0.02,
        treatment_cost=200.0,
        control_cost=100.0,
    )

    assert decision_impact(ctx) == "hedge_on_cost"


def test_decision_impact__rejects_null_match_with_null_cost_still_switches() -> None:
    """The rejects-null branch fires before cost suppression — switch is unaffected."""
    from eval_audit.report.decisions import decision_impact

    ctx = _ctx(
        rejects=True,
        delta_point=0.058,
        delta_lo=0.028,
        delta_hi=0.088,
        treatment_cost=None,
        control_cost=None,
        direction_matches_claim=True,
    )

    assert decision_impact(ctx) == "switch"


def test_decision_impact__dominated_with_null_cost_returns_drop_from_shortlist() -> None:
    """The dominance branch also fires before cost suppression."""
    from eval_audit.report.decisions import decision_impact

    ctx = _ctx(
        rejects=True,
        treatment_dominated=True,
        treatment_cost=None,
        control_cost=None,
    )

    assert decision_impact(ctx) == "drop_from_shortlist"


def _suppressed_row(agent_id: str, task_id: str, success: bool) -> dict:
    return {
        "agent_id": agent_id,
        "model_id": agent_id,
        "harness": "swe-bench-verified/openhands-public-submission-v1",
        "run_id": agent_id,
        "task_id": task_id,
        "task_category": None,
        "seed": None,
        "success": success,
        "partial_credit": None,
        "outcome_status": "graded",
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_in_by_model": {},
        "tokens_out_by_model": {},
        "latency_s": None,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": None,
        "reported_run_total_cost_usd": None,
        "cost_provenance": "cost_not_available",
        "rerun_metadata": {},
    }


def _stub_suppressed_study(treatment: str, control: str):
    from eval_audit.schema import StudySpec

    return StudySpec(
        id="suppressed-stub",
        benchmark="swe-bench-verified",
        analysis_mode="declared_reanalysis",
        data_observation="full_seen",
        harness="swe-bench-verified/openhands-public-submission-v1",
        primary_outcome={"name": "success_rate", "unit": "task", "direction": "higher_is_better"},
        agents=[{"id": treatment}, {"id": control}],
        design={
            "task_sampling": "fixed",
            "run_strategy": "observed",
            "observed_runs_per_agent": 1,
            "rerun_policy": "n/a",
        },
        inference={
            "alpha": 0.05,
            "correction_method": "holm_bonferroni",
            "comparison_family": "declared_claims",
            "target_mde": 0.05,
        },
        cost={
            "metrics": ["reconstructed_per_task_cost_usd"],
            "primary_view": "pareto_frontier",
        },
        claims=[
            {
                "id": "treat_vs_ctrl",
                "text": "treatment beats control",
                "treatment": treatment,
                "control": control,
                "outcome": "success_rate",
            }
        ],
    )


def _render_suppressed_report(tmp_path: Path) -> str:
    from eval_audit.report.markdown import render_report
    from eval_audit.stats import analyze

    rows = [_suppressed_row("treat", f"task_{i}", success=(i < 7)) for i in range(10)]
    rows += [_suppressed_row("ctrl", f"task_{i}", success=(i < 5)) for i in range(10)]
    runs = pl.DataFrame(rows, strict=False)
    study = _stub_suppressed_study("treat", "ctrl")

    result = analyze(study, runs, bootstrap_iterations=500, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=tmp_path,
        bootstrap_iterations=500,
        bootstrap_seed=42,
    )


def test_render__cost_not_available_caveat_block_present(tmp_path: Path) -> None:
    """The rendered report contains the cost_not_available caveat block."""
    text = _render_suppressed_report(tmp_path)
    assert "### Cost provenance caveat" in text
    assert "Cost provenance: cost_not_available" in text
    assert "expose no stable token, usage, or cost fields" in text


def test_render__cost_not_available_per_agent_table_omits_cost_columns(tmp_path: Path) -> None:
    """Per-agent summary table has no total_cost_usd or cost_per_success_usd columns."""
    text = _render_suppressed_report(tmp_path)
    assert "## Per-agent summary" in text
    # Cost columns absent in the per-agent table
    assert "| total_cost_usd |" not in text
    assert "| cost_per_success_usd |" not in text
    assert "Cost columns suppressed" in text


def test_render__cost_not_available_pareto_section_suppressed(tmp_path: Path) -> None:
    """Cost-quality view section points at the caveat block instead of a Pareto table."""
    text = _render_suppressed_report(tmp_path)
    assert "## Cost-quality view" in text
    assert "Cost-quality view suppressed" in text
    # The Pareto frontier table heading must be absent (descriptive prose
    # in the caveat block may still mention the words "Pareto frontier").
    assert "**Pareto frontier (max success_rate" not in text
    assert "Dominated agents:" not in text


def test_render__cost_not_available_robustness_review_row_present(tmp_path: Path) -> None:
    """Robustness Review names cost_not_available as a first-class row."""
    text = _render_suppressed_report(tmp_path)
    # The robustness table row reads `does not survive` with cost_not_available notes.
    assert "Cost provenance" in text
    assert "cost_not_available" in text
    assert "Pareto and cost-per-success suppressed" in text


def test_render__cost_not_available_audit_summary_no_cost_ratio(tmp_path: Path) -> None:
    """Audit summary stanza does NOT print 'treatment is X.XXx the control's cost'."""
    text = _render_suppressed_report(tmp_path)
    assert "the control's cost" not in text
    assert "no cost ratio is reported" in text


def test_render__cost_not_available_decision_not_hedge_on_cost(tmp_path: Path) -> None:
    """No claim row in the Claims table carries decision_impact=hedge_on_cost.

    The literal string `hedge_on_cost` may still appear in the caveat block
    as descriptive prose ("decision_impact cannot return `hedge_on_cost`");
    what must NOT appear is a Claims-table row whose final column is
    hedge_on_cost.
    """
    text = _render_suppressed_report(tmp_path)
    # Claims table rows end with `| <decision_impact> |`. Look for that exact
    # shape with hedge_on_cost.
    assert "| hedge_on_cost |" not in text


def test_render__cost_not_available_reviewer_pushback_flags_provenance(tmp_path: Path) -> None:
    """Reviewer pushback line names cost_not_available."""
    text = _render_suppressed_report(tmp_path)
    assert "cost provenance is cost_not_available" in text
