"""Acceptance tests for the errored-row denominator policy at the analyze() level.

Spec: openspec/changes/exhibit-b-tau-bench-reanalysis/specs/stats-engine/spec.md
"""

from __future__ import annotations

import polars as pl


def _row(
    *,
    agent_id: str,
    task_id: str,
    outcome_status: str,
    success: bool | None,
    harness: str = "tau_bench_tool_calling",
    reconstructed_cost: float | None = 0.10,
    reported_run_total: float = 5.00,
    cost_provenance: str = "as_reported_only",
) -> dict:
    return {
        "agent_id": agent_id,
        "model_id": agent_id,
        "harness": harness,
        "run_id": f"r-{agent_id}",
        "task_id": task_id,
        "task_category": None,
        "seed": None,
        "success": success,
        "partial_credit": None if success is None else float(success),
        "outcome_status": outcome_status,
        "tokens_in": 100,
        "tokens_out": 10,
        "tokens_in_by_model": {"m": 100},
        "tokens_out_by_model": {"m": 10},
        "latency_s": 1.0,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": reconstructed_cost,
        "reported_run_total_cost_usd": reported_run_total,
        "cost_provenance": cost_provenance,
        "rerun_metadata": {},
    }


def _stub_study(treatment: str, control: str, harness: str = "tau_bench_tool_calling"):
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


def _claude_taubench_rows() -> list[dict]:
    """Synthetic 50-task Claude frame: 22 graded-success, 25 graded-fail, 3 errored."""
    rows: list[dict] = []
    for i in range(22):
        rows.append(_row(
            agent_id="claude",
            task_id=f"t{i:02d}",
            outcome_status="graded",
            success=True,
        ))
    for i in range(22, 47):
        rows.append(_row(
            agent_id="claude",
            task_id=f"t{i:02d}",
            outcome_status="graded",
            success=False,
        ))
    for i in range(47, 50):
        rows.append(_row(
            agent_id="claude",
            task_id=f"t{i:02d}",
            outcome_status="errored",
            success=None,
            reconstructed_cost=None,
        ))
    return rows


def _o4mini_taubench_rows() -> list[dict]:
    """Synthetic 50-task o4-mini frame: 28 graded-success, 22 graded-fail, 0 errored."""
    rows: list[dict] = []
    for i in range(28):
        rows.append(_row(
            agent_id="o4mini",
            task_id=f"t{i:02d}",
            outcome_status="graded",
            success=True,
        ))
    for i in range(28, 50):
        rows.append(_row(
            agent_id="o4mini",
            task_id=f"t{i:02d}",
            outcome_status="graded",
            success=False,
        ))
    return rows


def test_errored_row_policy__claude_success_rate_matches_leaderboard_044() -> None:
    """WHEN analyze() is run on the Exhibit B fixture, where Claude has 50 task rows of
    which 3 have outcome_status == 'errored' and 22 have outcome_status == 'graded' AND
    success == True, THEN the Claude per-agent summary reports n_graded == 47,
    n_errored == 3, success_rate == 22/50 == 0.44.
    """
    from rigor.stats import analyze

    rows = _claude_taubench_rows() + _o4mini_taubench_rows()
    frame = pl.DataFrame(rows, strict=False)
    study = _stub_study("claude", "o4mini")

    result = analyze(study, frame, bootstrap_iterations=200, bootstrap_seed=42)

    by_id = {s.agent_id: s for s in result.per_agent}
    claude = by_id["claude"]
    assert claude.n_graded == 47
    assert claude.n_errored == 3
    assert abs(claude.success_rate - 0.44) < 1e-9
