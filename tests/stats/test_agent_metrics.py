"""Unit tests for per-agent summarization under errored-row policies."""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from eval_audit.stats.agent_metrics import (
    ErroredRowPolicy,
    summarize_agent,
    summarize_agents_for_pareto,
)
from eval_audit.stats.errors import CostProvenanceError


def _row(
    agent_id: str,
    task_id: str,
    *,
    success: bool = True,
    outcome_status: str = "graded",
    cost_provenance: str = "reconciled",
) -> dict[str, Any]:
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
        "outcome_status": outcome_status,
        "tokens_in": 100,
        "tokens_out": 10,
        "tokens_in_by_model": {"m": 100},
        "tokens_out_by_model": {"m": 10},
        "latency_s": 1.0,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": 0.001,
        "reported_run_total_cost_usd": 0.05,
        "cost_provenance": cost_provenance,
        "rerun_metadata": {},
    }


def test_summarize_agent__headline_includes_errored_in_denominator() -> None:
    rows = pl.DataFrame(
        [
            _row("a", "t1", success=True),
            _row("a", "t2", success=False, outcome_status="errored"),
        ]
    )
    summary = summarize_agent("a", rows, 0.05, policy=ErroredRowPolicy.headline)
    assert summary.n_graded == 1
    assert summary.n_errored == 1
    assert summary.success_rate == pytest.approx(0.5)


def test_summarize_agent__graded_only_excludes_errored_from_denominator() -> None:
    rows = pl.DataFrame(
        [
            _row("a", "t1", success=True),
            _row("a", "t2", success=False, outcome_status="errored"),
        ]
    )
    summary = summarize_agent("a", rows, 0.05, policy=ErroredRowPolicy.graded_only)
    assert summary.n_graded == 1
    assert summary.n_errored == 0
    assert summary.success_rate == pytest.approx(1.0)


def test_summarize_agent__cost_not_available_suppresses_cost_fields() -> None:
    rows = pl.DataFrame(
        [
            {
                **_row("a", "t1"),
                "reconstructed_per_task_cost_usd": None,
                "reported_run_total_cost_usd": None,
                "cost_provenance": "cost_not_available",
            }
        ]
    )
    summary = summarize_agent("a", rows, 0.05)
    assert summary.total_cost_usd is None
    assert summary.cost_per_success_usd is None


def test_summarize_agent__mixed_cost_provenance_raises() -> None:
    rows = pl.DataFrame(
        [
            _row("a", "t1", cost_provenance="reconciled"),
            {
                **_row("a", "t2"),
                "cost_provenance": "cost_not_available",
                "reconstructed_per_task_cost_usd": None,
                "reported_run_total_cost_usd": None,
            },
        ]
    )
    with pytest.raises(CostProvenanceError, match="mixed cost_provenance"):
        summarize_agent("a", rows, 0.05)


def test_pareto_helper_exclusion_preserves_cost_of_errored_only_runs() -> None:
    from tests.stats.test_analyze import _stub_study

    study = _stub_study("t", "c", "h")
    rows = []
    for agent_id in ("t", "c"):
        rows.extend(
            [
                {
                    **_row(agent_id, "graded-task"),
                    "run_id": f"{agent_id}-graded",
                    "reconstructed_per_task_cost_usd": None,
                    "reported_run_total_cost_usd": 0.05,
                },
                {
                    **_row(agent_id, "errored-task", outcome_status="errored"),
                    "run_id": f"{agent_id}-errored",
                    "success": None,
                    "partial_credit": None,
                    "reconstructed_per_task_cost_usd": None,
                    "reported_run_total_cost_usd": 0.10,
                },
            ]
        )
    runs = pl.DataFrame(rows)
    headline = summarize_agents_for_pareto(study, runs, 0.05)
    excluded = summarize_agents_for_pareto(study, runs, 0.05, policy=ErroredRowPolicy.graded_only)
    assert headline is not None and excluded is not None
    assert excluded["cost"].to_list() == pytest.approx([0.15, 0.15])
    assert excluded["cost"].to_list() == headline["cost"].to_list()
    assert headline["success_rate"].to_list() == [0.5, 0.5]
    assert excluded["success_rate"].to_list() == [1.0, 1.0]
