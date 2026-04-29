"""End-to-end synthetic-validation gate for the stats engine.

These tests load the synthetic known-truth dataset, run analyze() against it,
and assert recovery of the truth declared in scouting/synthetic/truth.json.
The full set runs as a CLI gate before any Exhibit A report is rendered.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture(scope="module")
def truth(scouting_dir: Path) -> dict:
    return json.loads((scouting_dir / "synthetic" / "truth.json").read_text())


@pytest.fixture(scope="module")
def analysis(scouting_dir: Path):
    from rigor.ingest.synthetic import SyntheticAdapter
    from rigor.schema import StudySpec
    from rigor.stats import analyze

    adapter = SyntheticAdapter()
    runs = adapter.load(scouting_dir / "synthetic")

    truth_data = json.loads((scouting_dir / "synthetic" / "truth.json").read_text())
    agent_ids = list(truth_data["agents"].keys())

    study = StudySpec(
        id="synthetic-validation",
        benchmark="synthetic",
        analysis_mode="exploratory",
        data_observation="full_seen",
        harness="synthetic",
        primary_outcome={"name": "success_rate", "unit": "task", "direction": "higher_is_better"},
        agents=[{"id": a} for a in agent_ids],
        design={
            "task_sampling": "fixed",
            "run_strategy": "observed",
            "observed_runs_per_agent": truth_data["n_seeds_per_task"],
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
                "id": f"primary_{truth_data['primary_pair'][0]}_vs_{truth_data['primary_pair'][1]}",
                "text": "primary pair from truth.json",
                "treatment": truth_data["primary_pair"][0],
                "control": truth_data["primary_pair"][1],
                "outcome": "success_rate",
            }
        ],
    )

    return analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)


@pytest.mark.synthetic_validation
def test_synthetic_validation__per_agent_success_rate_within_tolerance(analysis, truth) -> None:
    """Recovered per-agent success rate is within +/- 10pp of truth.json."""
    by_id = {s.agent_id: s for s in analysis.per_agent}
    for agent_id, expected in truth["agents"].items():
        observed = by_id[agent_id].success_rate
        target = expected["observed_success_rate"]
        assert abs(observed - target) <= 0.10, (
            f"agent={agent_id} observed={observed:.4f} target={target:.4f}"
        )


@pytest.mark.synthetic_validation
def test_synthetic_validation__pairwise_true_effect_ranking_matches(analysis, truth, scouting_dir: Path) -> None:
    """For every pair in truth.json, the recovered point estimate has the right sign."""
    from rigor.ingest.synthetic import SyntheticAdapter
    from rigor.stats.bootstrap import paired_task_bootstrap

    adapter = SyntheticAdapter()
    runs = adapter.load(scouting_dir / "synthetic")

    for pair in truth["pairwise_true_effects"]:
        a, b = pair["agent_a"], pair["agent_b"]
        true_delta = pair["true_delta"]
        if abs(true_delta) < 0.005:
            continue  # too close to call by sign
        boot = paired_task_bootstrap(
            runs.filter(pl.col("agent_id") == a),
            runs.filter(pl.col("agent_id") == b),
            outcome="success",
            n_iter=1_000,
            seed=42,
        )
        recovered_sign = 1 if boot.delta_point_estimate >= 0 else -1
        truth_sign = 1 if true_delta >= 0 else -1
        assert recovered_sign == truth_sign, (
            f"pair {a} vs {b}: true_delta={true_delta} recovered={boot.delta_point_estimate}"
        )


@pytest.mark.synthetic_validation
def test_synthetic_validation__pareto_membership_matches_truth(analysis, truth) -> None:
    """Pareto frontier membership matches truth.json exactly."""
    assert analysis.pareto_frontier == set(truth["pareto_frontier"])


@pytest.mark.synthetic_validation
def test_synthetic_validation__primary_pair_holm_does_not_reject(analysis, truth) -> None:
    """Holm-Bonferroni adjusted p-value for the primary pair does NOT reject at alpha=0.05."""
    primary_pair = tuple(truth["primary_pair"])
    matching = [
        c for c in analysis.claims
        if (c.treatment, c.control) == primary_pair or (c.control, c.treatment) == primary_pair
    ]
    assert matching, f"no claim matched primary pair {primary_pair}"
    claim = matching[0]
    expected_significant = truth["expected_holm_bonferroni_significant"]
    assert claim.rejects_null is expected_significant, (
        f"primary pair rejects_null={claim.rejects_null} adj_p={claim.adjusted_p_value} "
        f"expected_significant={expected_significant}"
    )
