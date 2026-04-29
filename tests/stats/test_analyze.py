"""Acceptance tests for analyze() and the cross-harness guard."""

from __future__ import annotations

import polars as pl


def _row(agent_id: str, task_id: str, harness: str) -> dict:
    return {
        "agent_id": agent_id,
        "model_id": agent_id,
        "harness": harness,
        "run_id": f"r-{agent_id}",
        "task_id": task_id,
        "task_category": None,
        "seed": None,
        "success": True,
        "partial_credit": True,
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
    from rigor.schema import StudySpec

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


def test_analyze__mixed_harness_comparison_is_rejected() -> None:
    """WHEN analyze is called on a frame with treatment harness=hal_generalist_agent and
    control harness=hal_tool_calling, THEN CrossHarnessComparisonError is raised naming
    both harnesses and both agent_ids.
    """
    import pytest

    from rigor.stats import CrossHarnessComparisonError, analyze

    rows = [
        _row("agent_t", "t01", "hal_generalist_agent"),
        _row("agent_c", "t01", "hal_tool_calling"),
    ]
    frame = pl.DataFrame(rows)
    study = _stub_study("agent_t", "agent_c", "hal_generalist_agent")

    with pytest.raises(CrossHarnessComparisonError) as exc_info:
        analyze(study, frame)

    msg = str(exc_info.value)
    assert "hal_generalist_agent" in msg
    assert "hal_tool_calling" in msg
    assert "agent_t" in msg
    assert "agent_c" in msg
