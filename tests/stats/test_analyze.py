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


def test_analyze__mixed_harness_comparison_is_rejected() -> None:
    """WHEN analyze is called on a frame with treatment harness=hal_generalist_agent and
    control harness=hal_tool_calling, THEN CrossHarnessComparisonError is raised naming
    both harnesses and both agent_ids.
    """
    import pytest

    from eval_audit.stats import CrossHarnessComparisonError, analyze

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


def test_analyze__rows_must_match_declared_study_harness() -> None:
    """WHEN both agents have rows under the same harness but not study.harness,
    THEN analyze rejects the comparison before reporting under the wrong label.
    """
    import pytest

    from eval_audit.stats import AnalysisInputError, analyze

    frame = pl.DataFrame(
        [
            _row("agent_t", "t01", "tau_bench_tool_calling"),
            _row("agent_t", "t02", "tau_bench_tool_calling"),
            _row("agent_c", "t01", "tau_bench_tool_calling"),
            _row("agent_c", "t02", "tau_bench_tool_calling"),
        ]
    )
    study = _stub_study("agent_t", "agent_c", "hal_generalist_agent")

    with pytest.raises(AnalysisInputError) as exc_info:
        analyze(study, frame)

    msg = str(exc_info.value)
    assert "hal_generalist_agent" in msg
    assert "tau_bench_tool_calling" in msg


def test_analyze__missing_claimed_agent_rows_fail_clearly() -> None:
    """WHEN a claimed treatment or control has no rows,
    THEN analyze names the missing agent before bootstrap execution.
    """
    import pytest

    from eval_audit.stats import AnalysisInputError, analyze

    frame = pl.DataFrame(
        [
            _row("agent_t", "t01", "hal_generalist_agent"),
            _row("agent_t", "t02", "hal_generalist_agent"),
        ]
    )
    study = _stub_study("agent_t", "agent_c", "hal_generalist_agent")

    with pytest.raises(AnalysisInputError) as exc_info:
        analyze(study, frame)

    msg = str(exc_info.value)
    assert "agent_c" in msg
    assert "no rows" in msg


def test_analyze__zero_success_cost_per_success_is_null() -> None:
    """WHEN an agent has cost but zero successful tasks,
    THEN cost_per_success_usd is unavailable rather than JSON-hostile infinity.
    """
    import pytest

    from eval_audit.stats import analyze

    rows = []
    for task_id in ("t01", "t02"):
        treatment = _row("agent_t", task_id, "hal_generalist_agent")
        treatment["success"] = False
        treatment["partial_credit"] = False
        control = _row("agent_c", task_id, "hal_generalist_agent")
        control["success"] = False
        control["partial_credit"] = False
        rows.extend([treatment, control])

    result = analyze(
        _stub_study("agent_t", "agent_c", "hal_generalist_agent"),
        pl.DataFrame(rows),
        bootstrap_iterations=20,
        bootstrap_seed=42,
    )

    by_id = {summary.agent_id: summary for summary in result.per_agent}
    assert by_id["agent_t"].total_cost_usd == pytest.approx(0.002)
    assert by_id["agent_c"].total_cost_usd == pytest.approx(0.002)
    assert by_id["agent_t"].cost_per_success_usd is None
    assert by_id["agent_c"].cost_per_success_usd is None


def test_analyze__benjamini_hochberg_dispatches_to_bh(monkeypatch) -> None:
    """WHEN correction_method is benjamini_hochberg,
    THEN analyze reports BH adjusted p-values rather than raw p-values.
    """
    import importlib

    from pytest import approx

    from eval_audit.schema import Claim, Inference
    from eval_audit.stats import analyze

    analyze_module = importlib.import_module("eval_audit.stats.analyze")
    raw_p_values = iter([0.001, 0.02, 0.04, 0.20])

    def fake_p_value(_treatment_rows, _control_rows) -> float:
        return next(raw_p_values)

    monkeypatch.setattr(analyze_module, "paired_task_p_value", fake_p_value)

    treatment = "agent_t"
    control = "agent_c"
    rows = [
        _row(treatment, "t01", "hal_generalist_agent"),
        _row(treatment, "t02", "hal_generalist_agent"),
        _row(control, "t01", "hal_generalist_agent"),
        _row(control, "t02", "hal_generalist_agent"),
    ]
    frame = pl.DataFrame(rows)
    study = _stub_study(treatment, control, "hal_generalist_agent").model_copy(
        update={
            "inference": Inference(
                alpha=0.05,
                correction_method="benjamini_hochberg",
                comparison_family="exploratory",
                target_mde=None,
            ),
            "claims": [
                Claim(
                    id="c1",
                    text="treatment beats control",
                    treatment=treatment,
                    control=control,
                    outcome="success_rate",
                ),
                Claim(
                    id="c2",
                    text="treatment beats control",
                    treatment=treatment,
                    control=control,
                    outcome="success_rate",
                ),
                Claim(
                    id="c3",
                    text="treatment beats control",
                    treatment=treatment,
                    control=control,
                    outcome="success_rate",
                ),
                Claim(
                    id="c4",
                    text="treatment beats control",
                    treatment=treatment,
                    control=control,
                    outcome="success_rate",
                ),
            ],
        }
    )

    result = analyze(study, frame, bootstrap_iterations=10, bootstrap_seed=42)

    adjusted = {claim.claim_id: claim.adjusted_p_value for claim in result.claims}
    assert adjusted["c1"] == approx(0.004)
    assert adjusted["c2"] == approx(0.04)
    assert adjusted["c3"] == approx(0.05333333333333334)
    assert adjusted["c4"] == approx(0.20)


def test_analyze__unsupported_outcome_fails_loudly() -> None:
    """WHEN analyze receives a StudySpec that bypassed validation with latency_s,
    THEN it raises before bootstrapping success as though the declaration were valid.
    """
    import pytest

    from eval_audit.stats import analyze

    study = _stub_study("agent_t", "agent_c", "hal_generalist_agent")
    bad_primary = study.primary_outcome.model_copy(update={"name": "latency_s"})
    bad_claim = study.claims[0].model_copy(update={"outcome": "latency_s"})
    bad_study = study.model_copy(update={"primary_outcome": bad_primary, "claims": [bad_claim]})
    frame = pl.DataFrame(
        [
            _row("agent_t", "t01", "hal_generalist_agent"),
            _row("agent_c", "t01", "hal_generalist_agent"),
        ]
    )

    with pytest.raises(ValueError) as exc_info:
        analyze(bad_study, frame)

    assert "success_rate" in str(exc_info.value)
