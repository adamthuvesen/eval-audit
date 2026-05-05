"""Schema tests for the cost_not_available provenance class."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def _swe_bench_row_kwargs() -> dict:
    return {
        "agent_id": "20251127_openhands_claude-opus-4-5",
        "model_id": "claude-opus-4-5-202511017",
        "harness": "swe-bench-verified/openhands-public-submission-v1",
        "run_id": "20251127_openhands_claude-opus-4-5",
        "task_id": "astropy__astropy-12907",
        "task_category": None,
        "seed": None,
        "success": True,
        "partial_credit": None,
        "outcome_status": "graded",
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_in_by_model": {},
        "tokens_out_by_model": {},
        "latency_s": None,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": None,
        "reported_run_total_cost_usd": None,
        "cost_provenance": "cost_not_available",
        "rerun_metadata": {"submission_dir": "20251127_openhands_claude-opus-4-5"},
    }


def test_cost_not_available__both_costs_null_is_accepted() -> None:
    """cost_not_available with both reconstructed and reported cost null constructs."""
    from eval_audit.schema import RunRecord

    record = RunRecord(**_swe_bench_row_kwargs())

    assert record.cost_provenance == "cost_not_available"
    assert record.reconstructed_per_task_cost_usd is None
    assert record.reported_run_total_cost_usd is None


def test_cost_not_available__rejects_non_null_reconstructed_cost() -> None:
    """cost_not_available + non-null reconstructed cost fails validation."""
    from eval_audit.schema import RunRecord

    kwargs = _swe_bench_row_kwargs()
    kwargs["reconstructed_per_task_cost_usd"] = 0.01

    with pytest.raises(ValidationError) as excinfo:
        RunRecord(**kwargs)

    msg = str(excinfo.value)
    assert "cost_not_available" in msg
    assert "reconstructed_per_task_cost_usd" in msg


def test_cost_not_available__rejects_non_null_reported_run_total() -> None:
    """cost_not_available + non-null reported run total fails validation."""
    from eval_audit.schema import RunRecord

    kwargs = _swe_bench_row_kwargs()
    kwargs["reported_run_total_cost_usd"] = 12.50

    with pytest.raises(ValidationError) as excinfo:
        RunRecord(**kwargs)

    msg = str(excinfo.value)
    assert "cost_not_available" in msg
    assert "reported_run_total_cost_usd" in msg


def test_reconciled__still_requires_reconstructed_cost_after_enum_extension() -> None:
    """The pre-existing reconciled rule still fires after adding cost_not_available."""
    from eval_audit.schema import RunRecord

    kwargs = _swe_bench_row_kwargs()
    kwargs["cost_provenance"] = "reconciled"
    kwargs["reconstructed_per_task_cost_usd"] = None

    with pytest.raises(ValidationError) as excinfo:
        RunRecord(**kwargs)

    msg = str(excinfo.value)
    assert "reconciled" in msg
    assert "reconstructed_per_task_cost_usd" in msg


def test_as_reported_only__null_reconstructed_still_accepted_after_enum_extension() -> None:
    """Existing as_reported_only path with null reconstructed cost stays unchanged."""
    from eval_audit.schema import RunRecord

    kwargs = _swe_bench_row_kwargs()
    kwargs["cost_provenance"] = "as_reported_only"
    kwargs["reconstructed_per_task_cost_usd"] = None
    kwargs["reported_run_total_cost_usd"] = 12.50

    record = RunRecord(**kwargs)

    assert record.cost_provenance == "as_reported_only"
    assert record.reconstructed_per_task_cost_usd is None
    assert record.reported_run_total_cost_usd == 12.50


def test_cost_not_available__reports_both_violations_together() -> None:
    """When both cost fields are non-null, the error names both fields."""
    from eval_audit.schema import RunRecord

    kwargs = _swe_bench_row_kwargs()
    kwargs["reconstructed_per_task_cost_usd"] = 0.01
    kwargs["reported_run_total_cost_usd"] = 12.50

    with pytest.raises(ValidationError) as excinfo:
        RunRecord(**kwargs)

    msg = str(excinfo.value)
    assert "reconstructed_per_task_cost_usd" in msg
    assert "reported_run_total_cost_usd" in msg
