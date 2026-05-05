"""Outcome expressions shared by analysis and bootstrap code."""

from __future__ import annotations

import polars as pl


def success_rate_numeric_expr() -> pl.Expr:
    """Numeric success-rate outcome with errored rows forced to failure."""
    return (
        pl.when(
            (pl.col("outcome_status") == "graded")
            & pl.col("success").fill_null(False).cast(pl.Boolean)
        )
        .then(1.0)
        .otherwise(0.0)
    )


def numeric_outcome_expr(outcome: str, *, use_outcome_status: bool) -> pl.Expr:
    if outcome == "success" and use_outcome_status:
        return success_rate_numeric_expr()
    return pl.col(outcome).cast(pl.Float64).fill_null(0.0)
