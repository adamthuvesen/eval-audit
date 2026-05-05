"""Acceptance test for the declared-agent rowless guard in analyze().

A declared agent that is not used by any claim still becomes a per-agent row in
the report and a candidate for the Pareto frontier. If the loaded run frame has
no rows for that agent, the analysis must fail loudly rather than fabricate a
zero-row summary.
"""

from __future__ import annotations

import polars as pl
import pytest


def _row(
    *,
    agent_id: str,
    task_id: str,
    success: bool,
) -> dict:
    return {
        "agent_id": agent_id,
        "model_id": agent_id,
        "harness": "tau_bench_tool_calling",
        "run_id": f"r-{agent_id}",
        "task_id": task_id,
        "task_category": None,
        "seed": None,
        "success": success,
        "partial_credit": float(success),
        "outcome_status": "graded",
        "tokens_in": 100,
        "tokens_out": 10,
        "tokens_in_by_model": {"m": 100},
        "tokens_out_by_model": {"m": 10},
        "latency_s": 1.0,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": 0.05,
        "reported_run_total_cost_usd": 0.50,
        "cost_provenance": "reconciled",
        "rerun_metadata": {},
    }


def _three_agent_study(harness: str = "tau_bench_tool_calling"):
    """Study with 3 declared agents but only one claim (treatment vs. control)."""
    from eval_audit.schema import StudySpec

    return StudySpec(
        id="stub",
        benchmark="stub",
        analysis_mode="declared_reanalysis",
        data_observation="full_seen",
        harness=harness,
        primary_outcome={"name": "success_rate", "unit": "task", "direction": "higher_is_better"},
        agents=[{"id": "treatment"}, {"id": "control"}, {"id": "extra_unclaimed"}],
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
                "treatment": "treatment",
                "control": "control",
                "outcome": "success_rate",
            }
        ],
    )


def test_analyze__declared_non_claim_agent_with_no_rows_raises() -> None:
    """A declared agent that is not in any claim and has no rows must raise.

    This is the methodology-correct behavior: a fabricated zero-row summary
    for a missing agent would otherwise distort the per-agent report table
    and the Pareto frontier inputs.
    """
    from eval_audit.stats.analyze import CrossHarnessComparisonError, analyze

    rows: list[dict] = []
    for i in range(4):
        rows.append(_row(agent_id="treatment", task_id=f"t{i:02d}", success=(i < 3)))
    for i in range(4):
        rows.append(_row(agent_id="control", task_id=f"t{i:02d}", success=(i < 1)))
    # Note: no rows for "extra_unclaimed" — the third declared agent.
    frame = pl.DataFrame(rows, strict=False)
    study = _three_agent_study()

    with pytest.raises(CrossHarnessComparisonError) as excinfo:
        analyze(study, frame, bootstrap_iterations=200, bootstrap_seed=42)

    msg = str(excinfo.value)
    assert "extra_unclaimed" in msg
    assert "no rows" in msg.lower()
