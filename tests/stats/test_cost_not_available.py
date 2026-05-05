"""Stats tests for cost_not_available cost suppression."""

from __future__ import annotations

import polars as pl
import pytest


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


def _reconciled_row(agent_id: str, task_id: str, success: bool) -> dict:
    return {
        "agent_id": agent_id,
        "model_id": agent_id,
        "harness": "h",
        "run_id": agent_id,
        "task_id": task_id,
        "task_category": None,
        "seed": None,
        "success": success,
        "partial_credit": success,
        "outcome_status": "graded",
        "tokens_in": 100,
        "tokens_out": 10,
        "tokens_in_by_model": {"m": 100},
        "tokens_out_by_model": {"m": 10},
        "latency_s": 1.0,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": 0.001,
        "reported_run_total_cost_usd": 0.05,
        "cost_provenance": "reconciled",
        "rerun_metadata": {},
    }


def _stub_study(treatment: str, control: str, harness: str):
    from eval_audit.schema import StudySpec

    return StudySpec(
        id="stub",
        benchmark="stub",
        analysis_mode="declared_reanalysis",
        data_observation="full_seen",
        harness=harness,
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
            "target_mde": None,
        },
        cost={
            "metrics": ["reconstructed_per_task_cost_usd"],
            "primary_view": "pareto_frontier",
        },
        claims=[
            {
                "id": "c1",
                "text": "treatment beats control",
                "treatment": treatment,
                "control": control,
                "outcome": "success_rate",
            }
        ],
    )


def test_agent_summary__cost_not_available_returns_none_costs() -> None:
    """All-cost-not-available agent summary has None for total_cost_usd and cost_per_success_usd."""
    from eval_audit.stats import analyze

    rows = [
        _suppressed_row("treat", f"task_{i}", success=(i < 3))
        for i in range(5)
    ]
    rows += [
        _suppressed_row("ctrl", f"task_{i}", success=(i < 2))
        for i in range(5)
    ]
    runs = pl.DataFrame(rows, strict=False)
    study = _stub_study("treat", "ctrl", "swe-bench-verified/openhands-public-submission-v1")

    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)

    by_id = {s.agent_id: s for s in result.per_agent}
    assert by_id["treat"].total_cost_usd is None
    assert by_id["treat"].cost_per_success_usd is None
    assert by_id["ctrl"].total_cost_usd is None
    assert by_id["ctrl"].cost_per_success_usd is None
    # Outcome accounting unchanged
    assert by_id["treat"].n_graded == 5
    assert by_id["treat"].success_rate == pytest.approx(0.6)
    assert by_id["ctrl"].success_rate == pytest.approx(0.4)


def test_agent_summary__mixed_provenance_raises() -> None:
    """An agent with both cost_not_available and reconciled rows raises CostProvenanceError."""
    from eval_audit.stats import analyze
    from eval_audit.stats.analyze import CostProvenanceError

    harness = "shared-harness"
    suppressed = _suppressed_row("treat", "t1", success=True)
    suppressed["harness"] = harness
    reconciled = _reconciled_row("treat", "t2", success=False)
    reconciled["harness"] = harness
    rows = [suppressed, reconciled]
    for i in range(2):
        ctrl_row = _reconciled_row("ctrl", f"task_{i}", success=(i < 1))
        ctrl_row["harness"] = harness
        rows.append(ctrl_row)
    runs = pl.DataFrame(rows, strict=False)
    study = _stub_study("treat", "ctrl", harness)

    with pytest.raises(CostProvenanceError) as excinfo:
        analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)

    msg = str(excinfo.value)
    assert "treat" in msg
    assert "cost_not_available" in msg
    assert "reconciled" in msg


def test_analyze__pareto_skipped_when_any_agent_suppressed() -> None:
    """Pareto frontier is empty and pareto_status flagged when any agent is cost-suppressed."""
    from eval_audit.stats import analyze

    rows = [
        _suppressed_row("treat", f"task_{i}", success=(i < 3))
        for i in range(5)
    ]
    rows += [
        _suppressed_row("ctrl", f"task_{i}", success=(i < 2))
        for i in range(5)
    ]
    runs = pl.DataFrame(rows, strict=False)
    study = _stub_study("treat", "ctrl", "swe-bench-verified/openhands-public-submission-v1")

    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)

    assert result.pareto_status == "suppressed_cost_not_available"
    assert result.pareto_frontier == set()


def test_analyze__pareto_computed_when_all_agents_reconciled() -> None:
    """Existing reconciled-cost path keeps Pareto computed and exposes pareto_status='computed'."""
    from eval_audit.stats import analyze

    rows = [_reconciled_row("treat", f"task_{i}", success=(i < 3)) for i in range(5)]
    rows += [_reconciled_row("ctrl", f"task_{i}", success=(i < 2)) for i in range(5)]
    runs = pl.DataFrame(rows, strict=False)
    study = _stub_study("treat", "ctrl", "h")

    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)

    assert result.pareto_status == "computed"
    by_id = {s.agent_id: s for s in result.per_agent}
    assert by_id["treat"].total_cost_usd == pytest.approx(5 * 0.001)
    assert by_id["ctrl"].total_cost_usd == pytest.approx(5 * 0.001)


def test_analyze__suppressed_agent_never_in_pareto_frontier_property() -> None:
    """Property: when one agent is cost-suppressed, the whole-study Pareto frontier is empty.

    Mix one all-reconciled agent with one all-cost_not_available agent. This is
    whole-agent (not mixed-row) suppression on ctrl, which is legal: analyze
    must run and return an empty frontier with pareto_status flagged.
    """
    from eval_audit.stats import analyze

    harness = "shared-harness"
    rows = []
    for i in range(5):
        r = _reconciled_row("treat", f"task_{i}", success=(i < 4))
        r["harness"] = harness
        rows.append(r)
    for i in range(5):
        r = _suppressed_row("ctrl", f"task_{i}", success=(i < 1))
        r["harness"] = harness
        rows.append(r)
    runs = pl.DataFrame(rows, strict=False)
    study = _stub_study("treat", "ctrl", harness)

    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)

    assert result.pareto_status == "suppressed_cost_not_available"
    assert result.pareto_frontier == set()
    suppressed_agents = {s.agent_id for s in result.per_agent if s.total_cost_usd is None}
    assert "ctrl" in suppressed_agents
    assert suppressed_agents.isdisjoint(result.pareto_frontier)


def test_analyze__suppressed_pareto_property_pure_suppressed_run() -> None:
    """When every agent is cost-suppressed, the returned frontier is empty (no agent leaks in)."""
    from eval_audit.stats import analyze

    rows = [_suppressed_row("treat", f"task_{i}", success=(i < 3)) for i in range(5)]
    rows += [_suppressed_row("ctrl", f"task_{i}", success=(i < 2)) for i in range(5)]
    runs = pl.DataFrame(rows, strict=False)
    study = _stub_study("treat", "ctrl", "swe-bench-verified/openhands-public-submission-v1")

    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)

    assert result.pareto_frontier == set()
    suppressed = {s.agent_id for s in result.per_agent if s.total_cost_usd is None}
    assert suppressed.isdisjoint(result.pareto_frontier)
