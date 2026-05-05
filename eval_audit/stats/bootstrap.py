"""Paired-task cluster bootstrap for delta uncertainty."""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import polars as pl


class BootstrapResult(NamedTuple):
    delta_point_estimate: float
    delta_ci_low: float
    delta_ci_high: float
    num_iterations: int
    seed: int


def _numeric_outcome_expr(outcome: str, *, use_outcome_status: bool) -> pl.Expr:
    if outcome == "success" and use_outcome_status:
        return (
            pl.when(
                (pl.col("outcome_status") == "graded")
                & pl.col("success").fill_null(False).cast(pl.Boolean)
            )
            .then(1.0)
            .otherwise(0.0)
        )
    return pl.col(outcome).cast(pl.Float64).fill_null(0.0)


def paired_task_bootstrap(
    arm_a: pl.DataFrame,
    arm_b: pl.DataFrame,
    *,
    outcome: str,
    n_iter: int = 10_000,
    alpha: float = 0.05,
    seed: int = 42,
) -> BootstrapResult:
    """Resample task_id values with replacement and recompute the delta of mean(outcome).

    Both arms must share the exact same set of task_id values; the function refuses
    to silently align mismatched task sets.
    """
    if n_iter < 1:
        raise ValueError(f"n_iter must be >= 1 (got {n_iter})")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be > 0 and < 1 (got {alpha})")
    for label, arm in (("arm_a", arm_a), ("arm_b", arm_b)):
        if "task_id" not in arm.columns:
            raise ValueError(f"{label} is missing required column 'task_id'")
        if arm.height == 0:
            raise ValueError(f"paired task bootstrap requires at least one paired task ({label} is empty)")
    for label, arm in (("arm_a", arm_a), ("arm_b", arm_b)):
        if outcome not in arm.columns:
            raise ValueError(f"{label} is missing outcome column {outcome!r}")

    tasks_a = set(arm_a["task_id"].to_list())
    tasks_b = set(arm_b["task_id"].to_list())
    if tasks_a != tasks_b:
        diff = tasks_a.symmetric_difference(tasks_b)
        raise ValueError(
            f"paired bootstrap requires identical task sets; "
            f"symmetric difference has {len(diff)} task_id(s)"
        )

    # Aggregate per-task means so each task contributes one value per arm.
    # Sort by task_id so the index space the rng samples over is stable across runs;
    # polars group_by returns rows in hash order by default, which makes seeded
    # bootstraps non-deterministic across processes.
    # Errored rows (success == None) are coerced to 0.0 here so they contribute as
    # failures to the per-task arm mean, matching the errored-row denominator policy.
    try:
        use_outcome_status = (
            outcome == "success"
            and "outcome_status" in arm_a.columns
            and "outcome_status" in arm_b.columns
        )
        outcome_expr = _numeric_outcome_expr(outcome, use_outcome_status=use_outcome_status)
        a_means = (
            arm_a.group_by("task_id")
            .agg(outcome_expr.mean().alias("_a"))
            .sort("task_id")
        )
        b_means = (
            arm_b.group_by("task_id")
            .agg(outcome_expr.mean().alias("_b"))
            .sort("task_id")
        )
    except Exception as exc:
        raise ValueError(f"outcome column {outcome!r} cannot be used numerically") from exc
    paired = a_means.join(b_means, on="task_id", how="inner").sort("task_id")
    if paired.height == 0:
        raise ValueError("paired task bootstrap requires at least one paired task")
    a_vec = paired["_a"].to_numpy()
    b_vec = paired["_b"].to_numpy()
    n_tasks = len(a_vec)

    point = float(a_vec.mean() - b_vec.mean())

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, n_tasks, size=(n_iter, n_tasks))
    deltas = a_vec[indices].mean(axis=1) - b_vec[indices].mean(axis=1)
    lo = float(np.quantile(deltas, alpha / 2))
    hi = float(np.quantile(deltas, 1 - alpha / 2))

    return BootstrapResult(
        delta_point_estimate=point,
        delta_ci_low=lo,
        delta_ci_high=hi,
        num_iterations=n_iter,
        seed=seed,
    )
