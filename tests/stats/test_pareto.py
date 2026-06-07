"""Acceptance tests for Pareto-frontier identification."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl


def test_pareto__synthetic_dataset_frontier_matches_truth(scouting_dir: Path) -> None:
    """WHEN the function is run on per-agent aggregates of the synthetic dataset,
    THEN the returned set equals {agent_a_strong, agent_b_strong_close, agent_c_mid}
    and excludes agent_d_weak, matching scouting/synthetic/truth.json.
    """
    from eval_audit.ingest.synthetic import SyntheticAdapter
    from eval_audit.stats import pareto_frontier

    adapter = SyntheticAdapter()
    frame = adapter.load(scouting_dir / "synthetic")

    per_agent = frame.group_by("agent_id").agg(
        pl.col("success").cast(pl.Int64).mean().alias("success_rate"),
        pl.col("reconstructed_per_task_cost_usd").sum().alias("cost"),
    )

    frontier = pareto_frontier(per_agent, success_col="success_rate", cost_col="cost")

    truth = json.loads((scouting_dir / "synthetic" / "truth.json").read_text())
    assert set(frontier) == set(truth["pareto_frontier"])
    assert "agent_d_weak" not in frontier
