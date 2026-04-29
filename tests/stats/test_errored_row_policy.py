"""Acceptance tests for the errored-row denominator policy at the analyze() level."""

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


def test_errored_row_policy__gaia_exhibit_a_byte_identical(repo_root) -> None:
    """WHEN analyze() is run on the Exhibit A GAIA fixture, where every row has
    outcome_status == 'graded' (n_errored == 0 for both agents),
    THEN every per-agent summary value (success_rate, n_graded, n_errored,
    total_cost_usd, cost_per_success_usd) is unchanged from the values committed
    in tests/report_snapshots/exhibit-a-report.md, because n_total == n_graded
    when n_errored == 0.
    """
    from rigor.ingest.hal_gaia import HalGaiaAdapter
    from rigor.schema import StudySpec
    from rigor.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")
    runs = HalGaiaAdapter().load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)

    by_id = {s.agent_id: s for s in result.per_agent}
    claude = by_id["HAL Generalist Agent (claude-3-7-sonnet-20250219)"]
    o4mini = by_id["HAL Generalist Agent (o4-mini-2025-04-16 high)"]

    # Pinned values from tests/report_snapshots/exhibit-a-report.md.
    assert claude.n_graded == 165
    assert claude.n_errored == 0
    assert abs(claude.success_rate - 0.5636) < 5e-5
    assert abs(claude.success_rate_ci_low - 0.4874) < 5e-5
    assert abs(claude.success_rate_ci_high - 0.6370) < 5e-5
    assert abs(claude.total_cost_usd - 130.68) < 0.01
    assert abs(claude.cost_per_success_usd - 1.41) < 0.01

    assert o4mini.n_graded == 165
    assert o4mini.n_errored == 0
    assert abs(o4mini.success_rate - 0.5455) < 5e-5
    assert abs(o4mini.total_cost_usd - 59.39) < 0.01
    assert abs(o4mini.cost_per_success_usd - 0.66) < 0.01


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


def test_errored_row_policy__paired_bootstrap_task_set_aligned_with_errored() -> None:
    """WHEN the bootstrap is invoked for the Exhibit B Claude-vs-o4-mini comparison,
    where Claude has 3 errored rows on tasks o4-mini graded,
    THEN the bootstrap does NOT raise ValueError('paired bootstrap requires identical
    task sets'); both arms contribute all 50 task_ids; errored Claude rows aggregate
    as 0.0 in their per-task arm mean.
    """
    from rigor.stats import analyze

    rows = _claude_taubench_rows() + _o4mini_taubench_rows()
    frame = pl.DataFrame(rows, strict=False)
    study = _stub_study("claude", "o4mini")

    result = analyze(study, frame, bootstrap_iterations=200, bootstrap_seed=42)

    # If the bootstrap raised, analyze() would have failed before returning.
    assert len(result.claims) == 1
    claim = result.claims[0]
    # Sanity: delta should be o4mini_rate - claude_rate = 0.56 - 0.44 = 0.12
    # (claim is treatment=claude vs control=o4mini, so delta = claude - o4mini = -0.12).
    assert abs(claim.delta_point_estimate - (0.44 - 0.56)) < 1e-9


def test_errored_row_policy__cost_per_success_uses_graded_successes() -> None:
    """WHEN the per-agent summary is computed for an agent with n_errored > 0,
    THEN cost_per_success_usd = total_cost_usd / successes where successes is the
    count of graded successes (an errored row cannot be a success), regardless of
    whether cost_provenance is reconciled or as_reported_only.
    """
    from rigor.stats import analyze

    # Reconciled path: 10 rows, 2 errored, 5 graded-successes, 3 graded-fail.
    # Each row's reconstructed_per_task_cost_usd = 0.10 (errored rows are None).
    # Expected total_cost_usd = 8 * 0.10 = 0.80; cost_per_success = 0.80 / 5 = 0.16.
    rows: list[dict] = []
    for i in range(5):
        rows.append(_row(
            agent_id="reconciled_agent",
            task_id=f"t{i:02d}",
            outcome_status="graded",
            success=True,
            harness="hal_generalist_agent",
            cost_provenance="reconciled",
            reconstructed_cost=0.10,
            reported_run_total=1.00,
        ))
    for i in range(5, 8):
        rows.append(_row(
            agent_id="reconciled_agent",
            task_id=f"t{i:02d}",
            outcome_status="graded",
            success=False,
            harness="hal_generalist_agent",
            cost_provenance="reconciled",
            reconstructed_cost=0.10,
            reported_run_total=1.00,
        ))
    for i in range(8, 10):
        rows.append(_row(
            agent_id="reconciled_agent",
            task_id=f"t{i:02d}",
            outcome_status="errored",
            success=None,
            harness="hal_generalist_agent",
            cost_provenance="reconciled",
            reconstructed_cost=None,
            reported_run_total=1.00,
        ))
    # Pair with a control agent so analyze() has a comparison to chew on.
    for i in range(10):
        rows.append(_row(
            agent_id="control_agent",
            task_id=f"t{i:02d}",
            outcome_status="graded",
            success=(i < 4),
            harness="hal_generalist_agent",
            cost_provenance="reconciled",
            reconstructed_cost=0.05,
            reported_run_total=0.50,
        ))

    frame = pl.DataFrame(rows, strict=False)
    study = _stub_study("reconciled_agent", "control_agent", harness="hal_generalist_agent")
    result = analyze(study, frame, bootstrap_iterations=200, bootstrap_seed=42)

    by_id = {s.agent_id: s for s in result.per_agent}
    agent = by_id["reconciled_agent"]
    assert agent.n_graded == 8
    assert agent.n_errored == 2
    # successes = 5 graded-true rows (errored rows can never count as success).
    assert abs(agent.total_cost_usd - 0.80) < 1e-9
    assert abs(agent.cost_per_success_usd - (0.80 / 5)) < 1e-9


# Hypothesis property test: for any random agent row distribution with errored,
# graded-success, and graded-fail counts, the recovered success_rate is consistent.

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402


@given(
    n_successes=st.integers(min_value=0, max_value=30),
    n_failures=st.integers(min_value=0, max_value=30),
    n_errored=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=40, deadline=None)
def test_errored_row_policy__property_success_rate_invariants(
    n_successes: int, n_failures: int, n_errored: int
) -> None:
    """For any randomly generated agent row distribution with
    0 <= n_errored <= n_total, success_rate * n_total equals the count of graded
    successes, AND success_rate <= n_graded / n_total (an errored row cannot
    increase the success rate vs the graded-only computation).
    """
    from rigor.stats import analyze

    n_total = n_successes + n_failures + n_errored
    if n_total < 2:  # bootstrap needs at least one task per arm to do anything
        return

    rows: list[dict] = []
    task_idx = 0
    for _ in range(n_successes):
        rows.append(_row(
            agent_id="agent",
            task_id=f"t{task_idx:03d}",
            outcome_status="graded",
            success=True,
        ))
        task_idx += 1
    for _ in range(n_failures):
        rows.append(_row(
            agent_id="agent",
            task_id=f"t{task_idx:03d}",
            outcome_status="graded",
            success=False,
        ))
        task_idx += 1
    for _ in range(n_errored):
        rows.append(_row(
            agent_id="agent",
            task_id=f"t{task_idx:03d}",
            outcome_status="errored",
            success=None,
            reconstructed_cost=None,
        ))
        task_idx += 1
    # Pair against a control with same task_id set so paired bootstrap can run.
    for i in range(n_total):
        rows.append(_row(
            agent_id="control",
            task_id=f"t{i:03d}",
            outcome_status="graded",
            success=False,
        ))

    frame = pl.DataFrame(rows, strict=False)
    study = _stub_study("agent", "control")
    result = analyze(study, frame, bootstrap_iterations=200, bootstrap_seed=42)

    by_id = {s.agent_id: s for s in result.per_agent}
    agent = by_id["agent"]
    assert agent.n_graded == n_successes + n_failures
    assert agent.n_errored == n_errored
    # Recovered count of graded successes = round(success_rate * n_total).
    recovered = round(agent.success_rate * n_total)
    assert recovered == n_successes
    # An errored row cannot increase success_rate vs the graded-only ratio.
    n_graded = n_successes + n_failures
    if n_graded > 0:
        graded_only_rate = n_successes / n_graded
        # success_rate uses n_total in denominator; n_total >= n_graded; so
        # success_rate <= graded_only_rate (with equality when n_errored == 0).
        assert agent.success_rate <= graded_only_rate + 1e-12
