"""Shared helpers for HAL-derived fixture adapters."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from eval_audit.ingest.base import (
    IngestContractError,
    check_locked_column_mapping,
    decode_token_counts,
    validate_run_records,
)


def load_hal_fixture(
    source_path: Path,
    *,
    locked_mapping: list[tuple[str, str]],
) -> tuple[pl.DataFrame, dict[str, Any], dict[str, Any]]:
    source_path = Path(source_path)
    sample_path = source_path / "sample.parquet"
    columns_path = source_path / "columns.json"
    cost_recon_path = source_path / "cost-reconciliation.json"
    provenance_path = source_path / "provenance.json"

    raw = pl.read_parquet(sample_path)
    check_locked_column_mapping(
        columns_path=columns_path,
        fixture_columns=raw.columns,
        locked_mapping=locked_mapping,
    )
    cost_recon = json.loads(cost_recon_path.read_text())
    provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    return raw, cost_recon, provenance


def decode_hal_token_counts(row: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    return (
        decode_token_counts(row["tokens_in_by_model"]),
        decode_token_counts(row["tokens_out_by_model"]),
    )


def hal_success_fields(
    row: dict[str, Any],
    *,
    partial_credit_column: str,
) -> tuple[bool | None, Any | None]:
    is_errored = row["outcome_status"] == "errored"
    success_raw = row["success_bool"]
    if success_raw is not None and (
        not isinstance(success_raw, (bool, int)) or success_raw not in (0, 1)
    ):
        raise IngestContractError(
            f"HAL success_bool must be boolean or integer 0/1, got {success_raw!r}"
        )
    success = None if is_errored or success_raw is None else bool(success_raw)
    partial_credit = None if is_errored else row[partial_credit_column]
    if isinstance(partial_credit, str):
        try:
            partial_credit = json.loads(partial_credit)
        except ValueError as exc:
            raise IngestContractError(
                f"HAL {partial_credit_column} must encode a boolean or number"
            ) from exc
        if not isinstance(partial_credit, (bool, int, float)):
            raise IngestContractError(
                f"HAL {partial_credit_column} must encode a boolean or number"
            )
    return success, partial_credit


def hal_common_record_fields(
    row: dict[str, Any],
    *,
    harness: str,
    success: bool | None,
    partial_credit: Any | None,
    tokens_in_by_model: dict[str, int],
    tokens_out_by_model: dict[str, int],
    reconstructed_cost: float | None,
    cost_provenance: str,
    rerun_metadata: dict[str, str],
    task_category: str | None = None,
) -> dict[str, Any]:
    timestamp = row["first_call_ts"]
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise IngestContractError(f"invalid HAL first_call_ts: {timestamp!r}") from exc
    return {
        "agent_id": row["agent_id"],
        "model_id": row["model_id"],
        "harness": harness,
        "run_id": row["run_id"],
        "task_id": row["task_id"],
        "task_category": task_category,
        "seed": None,
        "success": success,
        "partial_credit": partial_credit,
        "outcome_status": row["outcome_status"],
        "tokens_in": int(row["tokens_in_total"]),
        "tokens_out": int(row["tokens_out_total"]),
        "tokens_in_by_model": tokens_in_by_model,
        "tokens_out_by_model": tokens_out_by_model,
        "latency_s": (
            float(row["latency_total_s"]) if row["latency_total_s"] is not None else None
        ),
        "timestamp": timestamp,
        "reconstructed_per_task_cost_usd": reconstructed_cost,
        "reported_run_total_cost_usd": float(row["run_total_cost_usd"]),
        "cost_provenance": cost_provenance,
        "rerun_metadata": rerun_metadata,
    }


def validate_hal_harness(frame: pl.DataFrame, *, harness: str, adapter_name: str) -> None:
    validate_run_records(frame)
    if "harness" in frame.columns and not (frame["harness"] == harness).all():
        raise IngestContractError(
            f"{adapter_name} adapter expects every row to have harness={harness!r}"
        )
