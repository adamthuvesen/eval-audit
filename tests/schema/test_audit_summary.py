"""Round-trip AuditSummary schema against build_audit_summary output."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from eval_audit.report.presentation import resolve_study_presentation
from eval_audit.report.summary import build_audit_summary, summary_json_bytes
from eval_audit.schema import StudySpec
from eval_audit.schema.audit_summary import AuditSummary
from eval_audit.stats import analyze


def _minimal_study() -> StudySpec:
    return StudySpec(
        id="schema-roundtrip",
        benchmark="stub",
        analysis_mode="preregistered",
        data_observation="full_seen",
        harness="h",
        primary_outcome={"name": "success_rate", "unit": "task", "direction": "higher_is_better"},
        agents=[{"id": "t"}, {"id": "c"}],
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
                "text": "t beats c",
                "treatment": "t",
                "control": "c",
                "outcome": "success_rate",
            }
        ],
    )


def _row(agent_id: str, task_id: str, success: bool) -> dict:
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
        "outcome_status": "graded",
        "tokens_in": 10,
        "tokens_out": 1,
        "tokens_in_by_model": {"m": 10},
        "tokens_out_by_model": {"m": 1},
        "latency_s": 1.0,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": 0.01,
        "reported_run_total_cost_usd": 0.05,
        "cost_provenance": "reconciled",
        "rerun_metadata": {},
    }


def test_audit_summary__build_and_validate_round_trip() -> None:
    study = _minimal_study()
    rows = [_row("t", f"t{i}", i < 3) for i in range(4)]
    rows += [_row("c", f"t{i}", i < 1) for i in range(4)]
    runs = pl.DataFrame(rows, strict=False)
    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=1)
    presentation = resolve_study_presentation(study, runs, result, Path("."))
    summary = build_audit_summary(
        result=result,
        study=study,
        runs=runs,
        presentation=presentation,
        readiness="ready",
        artifact_paths={},
    )
    raw = json.loads(summary_json_bytes(summary).decode())
    restored = AuditSummary.model_validate(raw)
    assert restored.study_id == study.id
    assert len(restored.claims) == 1
    assert restored.claims[0].verdict in {
        "switch",
        "hold",
        "drop_from_shortlist",
        "rerun_more_n",
        "hedge_on_cost",
        "inconclusive_no_action",
    }
