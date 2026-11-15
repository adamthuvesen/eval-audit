"""Adversarial checks for whole-study sensitivity scenarios."""

from __future__ import annotations

from dataclasses import replace

import polars as pl
import pytest

from eval_audit.report.sections.robustness import robustness_errored_policy
from eval_audit.report.sensitivity import compute_sensitivity_rows
from eval_audit.schema import AgentRef, Claim
from eval_audit.stats import analyze, paired_task_bootstrap, paired_task_p_value
from eval_audit.stats.sensitivity import recompute_scenario
from tests.stats.test_analyze import _row, _stub_study


def _family():
    study = _stub_study("t", "c", "h")
    study = study.model_copy(
        update={
            "agents": [AgentRef(id=a) for a in ("t", "c", "u", "v")],
            "claims": [
                study.claims[0],
                Claim(
                    id="c2", text="u beats v", treatment="u", control="v", outcome="success_rate"
                ),
            ],
        }
    )
    rows = []
    for i in range(20):
        for agent in ("t", "c", "u", "v"):
            row = _row(agent, f"task-{i:02d}", "h")
            row["success"] = {"t": i < 4, "c": False, "u": i < 10, "v": i < 5 or i >= 10}[agent]
            row["partial_credit"] = row["success"]
            row["reconstructed_per_task_cost_usd"] = 1.0 if agent in ("t", "c") else 10.0
            if agent == "u" and i >= 10:
                row["success"] = None
                row["partial_credit"] = None
                row["outcome_status"] = "errored"
            rows.append(row)
    return study, pl.DataFrame(rows)


def test_error_exclusion_updates_other_claims_in_the_family() -> None:
    study, runs = _family()
    baseline = analyze(study, runs, bootstrap_iterations=500, bootstrap_seed=7)
    scenario = recompute_scenario(study, runs, baseline, exclude_errored=True)
    original = baseline.claims[0]
    changed = scenario.result.claims[0]
    assert changed.raw_p_value == original.raw_p_value
    assert not original.rejects_null
    assert changed.rejects_null
    assert changed.adjusted_p_value < original.adjusted_p_value
    rows = compute_sensitivity_rows(original, runs, study, baseline)
    assert rows[0].verdict == "inconclusive_no_action"
    assert next(row for row in rows if row.dimension == "errored_policy").verdict == "switch"


def test_error_exclusion_keeps_incurred_costs() -> None:
    study, runs = _family()
    baseline = analyze(study, runs, bootstrap_iterations=50)
    scenario = recompute_scenario(study, runs, baseline, exclude_errored=True)
    original_costs = {a.agent_id: a.total_cost_usd for a in baseline.per_agent}
    assert {a.agent_id: a.total_cost_usd for a in scenario.result.per_agent} == original_costs


def test_unavailable_claim_retains_original_correction_family() -> None:
    study, runs = _family()
    runs = runs.with_columns(
        pl.when((pl.col("agent_id") == "u") & (pl.col("task_id") != "task-00"))
        .then(pl.lit("errored"))
        .otherwise(pl.col("outcome_status"))
        .alias("outcome_status")
    ).with_columns(
        pl.when(pl.col("outcome_status") == "errored")
        .then(None)
        .otherwise(pl.col("success"))
        .alias("success"),
        pl.when(pl.col("outcome_status") == "errored")
        .then(None)
        .otherwise(pl.col("partial_credit"))
        .alias("partial_credit"),
    )
    baseline = analyze(study, runs, bootstrap_iterations=50)
    scenario = recompute_scenario(study, runs, baseline, exclude_errored=True)
    assert "c2" in scenario.unavailable_claims
    assert [c.claim_id for c in scenario.result.claims] == ["c1"]
    assert scenario.result.claims[0].adjusted_p_value == pytest.approx(
        2 * baseline.claims[0].raw_p_value
    )
    rows = compute_sensitivity_rows(baseline.claims[1], runs, study, baseline)
    excluded = next(row for row in rows if row.dimension == "errored_policy")
    assert excluded.verdict is None
    assert "fewer than two paired graded tasks" in (excluded.unavailable_reason or "")
    assert robustness_errored_policy(rows, rows[0].verdict or "")[0] == "not assessed"


def test_alpha_updates_bootstrap_and_agent_intervals() -> None:
    study, runs = _family()
    baseline = analyze(study, runs, bootstrap_iterations=2_000)
    strict = recompute_scenario(study, runs, baseline, alpha=0.01).result
    loose = recompute_scenario(study, runs, baseline, alpha=0.10).result
    assert strict.settings == replace(baseline.settings, alpha=0.01)
    assert strict.claims[0].delta_ci_low < loose.claims[0].delta_ci_low
    assert strict.claims[0].delta_ci_high > loose.claims[0].delta_ci_high
    assert strict.per_agent[0].success_rate_ci_low < loose.per_agent[0].success_rate_ci_low
    assert strict.per_agent[0].success_rate_ci_high > loose.per_agent[0].success_rate_ci_high


@pytest.mark.parametrize(
    "statistic", [paired_task_p_value, lambda a, b: paired_task_bootstrap(a, b, outcome="success")]
)
def test_paired_statistics_refuse_different_task_sets(statistic) -> None:
    a = pl.DataFrame({"task_id": ["one", "two"], "success": [True, False]})
    b = pl.DataFrame({"task_id": ["two", "three"], "success": [False, True]})
    with pytest.raises(ValueError, match="identical task sets"):
        statistic(a, b)


def test_paired_statistics_are_stable_under_task_and_replication_order() -> None:
    a = pl.DataFrame(
        {"task_id": ["one", "one", "two", "two"], "success": [True, False, True, True]}
    )
    b = pl.DataFrame(
        {"task_id": ["two", "two", "one", "one"], "success": [True, False, False, False]}
    )
    assert paired_task_p_value(a, b) == paired_task_p_value(a.reverse(), b.reverse())
    assert paired_task_bootstrap(a, b, outcome="success", n_iter=100) == paired_task_bootstrap(
        a.reverse(), b.reverse(), outcome="success", n_iter=100
    )


def test_unclaimed_agent_errors_can_change_an_error_free_claim_through_pareto() -> None:
    study = _stub_study("t", "c", "h")
    study = study.model_copy(update={"agents": [*study.agents, AgentRef(id="u")]})
    rows = []
    for task in range(20):
        for agent in ("t", "c", "u"):
            row = _row(agent, f"task-{task:02d}", "h")
            row["success"] = {"t": task < 4, "c": False, "u": task < 3}[agent]
            row["partial_credit"] = row["success"]
            row["reconstructed_per_task_cost_usd"] = 0.1 if agent == "u" else 1.0
            if agent == "u" and task >= 6:
                row["success"] = None
                row["partial_credit"] = None
                row["outcome_status"] = "errored"
            rows.append(row)
    runs = pl.DataFrame(rows)
    baseline = analyze(study, runs, bootstrap_iterations=100)
    sensitivity = compute_sensitivity_rows(baseline.claims[0], runs, study, baseline)
    assert sensitivity[0].verdict == "switch"
    assert (
        next(row for row in sensitivity if row.dimension == "errored_policy").verdict
        == "drop_from_shortlist"
    )


@pytest.mark.parametrize("missing_cost_agents", [("t", "c", "unclaimed"), ("unclaimed",), ()])
def test_unclaimed_agent_without_grades_only_blocks_available_pareto(
    missing_cost_agents: tuple[str, ...],
) -> None:
    study = _stub_study("t", "c", "h")
    study.agents.append(AgentRef(id="unclaimed"))
    rows = []
    for task in range(20):
        for agent in ("t", "c", "unclaimed"):
            row = _row(agent, f"task-{task:02d}", "h")
            row["success"] = row["partial_credit"] = agent == "t" and task < 10
            if agent in missing_cost_agents:
                row["cost_provenance"] = "cost_not_available"
                row["reconstructed_per_task_cost_usd"] = None
                row["reported_run_total_cost_usd"] = None
            if agent == "unclaimed":
                row["success"] = row["partial_credit"] = None
                row["outcome_status"] = "errored"
            rows.append(row)
    runs = pl.DataFrame(rows)
    baseline = analyze(study, runs, bootstrap_iterations=100)
    scenario = recompute_scenario(study, runs, baseline, exclude_errored=True)
    assert scenario.result.claims[0].raw_p_value == baseline.claims[0].raw_p_value
    assert scenario.result.pareto_status == baseline.pareto_status
    sensitivity = compute_sensitivity_rows(baseline.claims[0], runs, study, baseline)
    baseline_row = sensitivity[0]
    excluded_row = next(row for row in sensitivity if row.dimension == "errored_policy")
    assert baseline_row.verdict == "switch"
    if missing_cost_agents:
        assert not scenario.unavailable_claims
        assert not scenario.result.pareto_frontier
        assert excluded_row.verdict == baseline_row.verdict
        assert excluded_row.unavailable_reason is None
    else:
        assert excluded_row.verdict is None
        assert "Pareto frontier unavailable" in (excluded_row.unavailable_reason or "")
