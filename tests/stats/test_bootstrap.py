"""Acceptance tests for paired-task cluster bootstrap."""

from __future__ import annotations

import polars as pl


def _arm(agent_id: str, success_rate: float, n_tasks: int = 30) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "agent_id": [agent_id] * n_tasks,
            "task_id": [f"task_{i:03d}" for i in range(n_tasks)],
            "success": [1 if i / n_tasks < success_rate else 0 for i in range(n_tasks)],
        }
    )


def test_bootstrap__identical_arms_produce_ci_containing_zero() -> None:
    """WHEN the bootstrap is run with both arms equal to the same per-task success vector,
    THEN the returned CI contains 0.0.
    """
    from eval_audit.stats import paired_task_bootstrap

    arm = _arm("a", 0.6)
    same = arm.with_columns(pl.lit("b").alias("agent_id"))

    result = paired_task_bootstrap(arm, same, outcome="success", n_iter=500, seed=42)

    assert result.delta_ci_low <= 0.0 <= result.delta_ci_high
    assert result.delta_point_estimate == 0.0


def test_bootstrap__mismatched_task_sets_raise() -> None:
    """WHEN the two input frames have different task_id sets,
    THEN the function raises ValueError naming the symmetric difference size.
    """
    import pytest

    from eval_audit.stats import paired_task_bootstrap

    arm_a = _arm("a", 0.6, n_tasks=30)
    arm_b = pl.DataFrame(
        {
            "agent_id": ["b"] * 25,
            "task_id": [f"task_{i:03d}" for i in range(5, 30)],
            "success": [1] * 25,
        }
    )

    with pytest.raises(ValueError) as exc_info:
        paired_task_bootstrap(arm_a, arm_b, outcome="success", n_iter=10, seed=0)

    assert "5" in str(exc_info.value)  # 5 task_ids missing from arm_b vs arm_a


def test_bootstrap__missing_outcome_column_raises() -> None:
    """WHEN the requested outcome column is absent,
    THEN the bootstrap raises a clear ValueError naming it.
    """
    import pytest

    from eval_audit.stats import paired_task_bootstrap

    frame = pl.DataFrame(
        {
            "task_id": ["a", "b"],
            "success": [True, False],
        }
    )

    with pytest.raises(ValueError) as exc_info:
        paired_task_bootstrap(frame, frame, outcome="partial_credit")

    assert "partial_credit" in str(exc_info.value)
