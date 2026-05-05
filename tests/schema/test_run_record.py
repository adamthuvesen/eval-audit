"""Acceptance tests for the RunRecord schema."""

from __future__ import annotations

from datetime import UTC, datetime


def _gaia_row_kwargs() -> dict:
    return {
        "agent_id": "gaia_hg_claude37",
        "model_id": "claude-3-7-sonnet",
        "harness": "hal_generalist_agent",
        "run_id": "run_001",
        "task_id": "task_abc",
        "task_category": None,
        "seed": None,
        "success": True,
        "partial_credit": True,
        "outcome_status": "graded",
        "tokens_in": 12345,
        "tokens_out": 678,
        "tokens_in_by_model": {"claude-3-7-sonnet": 12345},
        "tokens_out_by_model": {"claude-3-7-sonnet": 678},
        "latency_s": 4.5,
        "timestamp": datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC),
        "reconstructed_per_task_cost_usd": 0.0457,
        "reported_run_total_cost_usd": 130.68,
        "cost_provenance": "reconciled",
        "rerun_metadata": {"git_commit": "abc123"},
    }


def test_run_record__valid_gaia_row_constructs() -> None:
    """WHEN a row from the GAIA fixture is constructed via the RunRecord model with all
    required fields populated, THEN the model instance is created with no validation
    error and all listed fields are accessible.
    """
    from eval_audit.schema import RunRecord

    record = RunRecord(**_gaia_row_kwargs())

    assert record.agent_id == "gaia_hg_claude37"
    assert record.harness == "hal_generalist_agent"
    assert record.success is True
    assert record.outcome_status == "graded"
    assert record.cost_provenance == "reconciled"
    assert record.tokens_in_by_model["claude-3-7-sonnet"] == 12345
    assert record.reconstructed_per_task_cost_usd == 0.0457


def test_run_record__errored_task_is_preserved_not_dropped() -> None:
    """WHEN a row has outcome_status='errored' and success=None,
    THEN the model accepts it without raising, and success remains None.
    """
    from eval_audit.schema import RunRecord

    kwargs = _gaia_row_kwargs()
    kwargs["outcome_status"] = "errored"
    kwargs["success"] = None
    kwargs["partial_credit"] = None

    record = RunRecord(**kwargs)

    assert record.outcome_status == "errored"
    assert record.success is None


def test_run_record__errored_task_cannot_carry_success_or_partial_credit() -> None:
    """WHEN an errored row carries success or partial_credit,
    THEN validation fails before analysis can treat that row inconsistently.
    """
    import pytest
    from pydantic import ValidationError

    from eval_audit.schema import RunRecord

    for field, value in (("success", True), ("partial_credit", 1.0)):
        kwargs = _gaia_row_kwargs()
        kwargs["outcome_status"] = "errored"
        kwargs["success"] = None
        kwargs["partial_credit"] = None
        kwargs[field] = value

        with pytest.raises(ValidationError) as exc_info:
            RunRecord(**kwargs)

        msg = str(exc_info.value)
        assert "errored" in msg
        assert field in msg


def test_run_record__reconciled_cost_provenance_demands_reconstructed_value() -> None:
    """WHEN construction is attempted with cost_provenance='reconciled' and
    reconstructed_per_task_cost_usd=None, THEN validation fails with an error
    naming both fields.
    """
    import pytest
    from pydantic import ValidationError

    from eval_audit.schema import RunRecord

    kwargs = _gaia_row_kwargs()
    kwargs["reconstructed_per_task_cost_usd"] = None

    with pytest.raises(ValidationError) as exc_info:
        RunRecord(**kwargs)

    msg = str(exc_info.value)
    assert "reconciled" in msg
    assert "reconstructed_per_task_cost_usd" in msg


def test_run_record__negative_numeric_fields_fail_validation() -> None:
    """WHEN numeric counts, costs, or latency are negative,
    THEN validation fails with an error naming the invalid field.
    """
    import pytest
    from pydantic import ValidationError

    from eval_audit.schema import RunRecord

    cases = [
        ("tokens_in", -1),
        ("tokens_out", -1),
        ("tokens_in_by_model", {"claude-3-7-sonnet": -1}),
        ("tokens_out_by_model", {"claude-3-7-sonnet": -1}),
        ("latency_s", -0.1),
        ("reconstructed_per_task_cost_usd", -0.01),
        ("reported_run_total_cost_usd", -1.0),
    ]
    for field, value in cases:
        kwargs = _gaia_row_kwargs()
        kwargs[field] = value

        with pytest.raises(ValidationError) as exc_info:
            RunRecord(**kwargs)

        assert field in str(exc_info.value)


def test_run_record__provenance_enum_rejects_unknown_values() -> None:
    """WHEN a RunRecord is constructed with cost_provenance='totally_made_up',
    THEN validation fails with an enum error.
    """
    import pytest
    from pydantic import ValidationError

    from eval_audit.schema import RunRecord

    kwargs = _gaia_row_kwargs()
    kwargs["cost_provenance"] = "totally_made_up"

    with pytest.raises(ValidationError) as exc_info:
        RunRecord(**kwargs)

    assert "cost_provenance" in str(exc_info.value)
