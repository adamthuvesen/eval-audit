"""Regenerate examples/byo-minimal/runs.parquet from inline data.

This script builds a 20-row canonical RunRecord-shaped parquet for a toy
2-agent 10-task audit (alice 0.80, bob 0.40 success rate). Every BYO user
ends up writing something like this; treat it as the worked example for
"how do I get my data into eval-audit's canonical shape?".

Usage:

    python examples/byo-minimal/make_runs.py

The committed runs.parquet must round-trip from this script (a test in
tests/examples/test_byo_minimal_round_trip.py pins this).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

# Per-task success outcomes. alice gets 8 of 10 right, bob gets 4 of 10.
# Deterministic per-task so anyone reading the script can verify the math.
ALICE_SUCCESS = [True, True, True, True, True, True, True, True, False, False]
BOB_SUCCESS = [True, True, True, True, False, False, False, False, False, False]


def _row(
    *,
    agent_id: str,
    task_id: str,
    success: bool,
    cost: float,
    tokens_in: int,
    tokens_out: int,
) -> dict:
    return {
        "agent_id": agent_id,
        "model_id": agent_id,
        "harness": "byo-minimal",
        "run_id": f"run-{agent_id}",
        "task_id": task_id,
        "task_category": None,
        "seed": 0,
        "success": success,
        "partial_credit": float(success),
        "outcome_status": "graded",
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_in_by_model": {agent_id: tokens_in},
        "tokens_out_by_model": {agent_id: tokens_out},
        "latency_s": 1.0,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": cost,
        "reported_run_total_cost_usd": cost * 10,  # 10 tasks per run
        "cost_provenance": "reconciled",
        "rerun_metadata": {"source": "examples/byo-minimal"},
    }


def build_frame() -> pl.DataFrame:
    rows: list[dict] = []
    for i, success in enumerate(ALICE_SUCCESS, start=1):
        rows.append(
            _row(
                agent_id="alice",
                task_id=f"task_{i:02d}",
                success=success,
                cost=0.10,
                tokens_in=1000,
                tokens_out=200,
            )
        )
    for i, success in enumerate(BOB_SUCCESS, start=1):
        rows.append(
            _row(
                agent_id="bob",
                task_id=f"task_{i:02d}",
                success=success,
                cost=0.05,
                tokens_in=800,
                tokens_out=150,
            )
        )
    return pl.DataFrame(rows, strict=False)


def main() -> None:
    frame = build_frame()
    out_path = Path(__file__).resolve().parent / "runs.parquet"
    frame.write_parquet(out_path)
    print(f"wrote {out_path} ({frame.height} rows)")


if __name__ == "__main__":
    main()
