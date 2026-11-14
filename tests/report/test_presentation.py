"""Tests for study presentation resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from eval_audit.report.presentation import (
    resolve_report_cost_provenance,
    resolve_study_presentation,
)
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats import analyze


def _study(*, mode: str = "declared_reanalysis") -> StudySpec:
    return StudySpec.model_validate(
        {
            "id": "presentation-test",
            "benchmark": "stub",
            "analysis_mode": mode,
            "data_observation": "full_seen",
            "harness": "h",
            "primary_outcome": {
                "name": "success_rate",
                "unit": "task",
                "direction": "higher_is_better",
            },
            "agents": [{"id": "t"}, {"id": "c"}],
            "design": {
                "task_sampling": "fixed",
                "run_strategy": "observed",
                "observed_runs_per_agent": 1,
                "rerun_policy": "n/a",
            },
            "inference": {
                "alpha": 0.05,
                "correction_method": "holm_bonferroni",
                "comparison_family": "declared_claims",
                "target_mde": None,
            },
            "cost": {
                "metrics": ["reconstructed_per_task_cost_usd"],
                "primary_view": "pareto_frontier",
            },
            "claims": [
                {
                    "id": "c1",
                    "text": "t beats c",
                    "treatment": "t",
                    "control": "c",
                    "outcome": "success_rate",
                }
            ],
        }
    )


def _row(cost_provenance: str) -> dict[str, Any]:
    return {
        "agent_id": "t",
        "model_id": "t",
        "harness": "h",
        "run_id": "t",
        "task_id": "t1",
        "task_category": None,
        "seed": None,
        "success": True,
        "partial_credit": True,
        "outcome_status": "graded",
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_in_by_model": {},
        "tokens_out_by_model": {},
        "latency_s": None,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": None,
        "reported_run_total_cost_usd": None,
        "cost_provenance": cost_provenance,
        "rerun_metadata": {},
    }


def test_resolve_report_cost_provenance__declared_reanalysis_without_recon() -> None:
    study = _study(mode="declared_reanalysis")
    runs = pl.DataFrame([_row("cost_not_available"), _row("cost_not_available")])
    assert (
        resolve_report_cost_provenance(study, runs, {}) == CostProvenance.COST_NOT_AVAILABLE.value
    )
    runs_recon = pl.DataFrame([_row("reconciled"), _row("reconciled")])
    assert resolve_report_cost_provenance(study, runs_recon, {}) == "reconciled"


def test_resolve_study_presentation__flags_under_cost_suppression() -> None:
    study = _study()
    rows = [_row("cost_not_available")]
    rows.append({**_row("cost_not_available"), "agent_id": "c", "model_id": "c", "run_id": "c"})
    runs = pl.DataFrame(rows, strict=False)
    result = analyze(study, runs, bootstrap_iterations=100, bootstrap_seed=1)
    presentation = resolve_study_presentation(study, runs, result, Path())
    assert presentation.pareto_suppressed is True
    assert presentation.show_cost_columns is False
    assert presentation.cost_gap_sensitivity_applicable is False
    assert presentation.hedge_on_cost_allowed is False
