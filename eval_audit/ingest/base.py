"""Adapter Protocol shared by every benchmark ingest implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

import polars as pl
from pydantic import ValidationError

from eval_audit.schema import RunRecord


class IngestContractError(RuntimeError):
    """Raised when a fixture or loaded frame violates the canonical contract."""


@runtime_checkable
class IngestAdapter(Protocol):
    """Adapter contract for producing canonical RunRecord-shaped frames."""

    name: str

    def load(self, source_path: Path) -> pl.DataFrame: ...

    def validate(self, frame: pl.DataFrame) -> None: ...


def check_locked_column_mapping(
    *,
    columns_path: Path,
    fixture_columns: list[str],
    locked_mapping: list[tuple[str, str]],
) -> None:
    """Verify the locked semantic-role mapping against columns.json and parquet columns."""
    if not columns_path.exists():
        raise IngestContractError(
            f"locked column mapping check requires {columns_path}; file is missing"
        )
    declared = json.loads(columns_path.read_text())
    declared_pairs = {
        (col["raw_name"], col["semantic_role"])
        for table in declared.get("tables", [])
        for col in table.get("columns", [])
    }
    fixture_set = set(fixture_columns)

    failures: list[str] = []
    for raw_name, semantic_role in locked_mapping:
        if (raw_name, semantic_role) not in declared_pairs:
            failures.append(
                f"locked mapping ({raw_name!r} -> {semantic_role!r}) "
                f"not present in {columns_path.name}"
            )
        if raw_name not in fixture_set:
            failures.append(
                f"locked raw column {raw_name!r} expected in fixture but found columns: "
                f"{sorted(fixture_set)}"
            )
    if failures:
        raise IngestContractError("; ".join(failures))


def decode_token_counts(value: str | None) -> dict[str, int]:
    if value in (None, ""):
        return {}
    decoded = json.loads(value)
    return {str(k): int(v) for k, v in decoded.items()}


def assert_canonical_schema(frame: pl.DataFrame) -> None:
    """Raise IngestContractError if the frame's columns don't match RunRecord."""
    expected = set(RunRecord.model_fields.keys())
    actual = set(frame.columns)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing columns: {sorted(missing)}")
        if extra:
            parts.append(f"unexpected columns: {sorted(extra)}")
        raise IngestContractError("; ".join(parts))


def validate_run_records(frame: pl.DataFrame) -> None:
    """Validate every row through the canonical RunRecord Pydantic model.

    Raises ``IngestContractError`` with a one-line message naming the row
    index, field path, and bad value. The original ``pydantic.ValidationError``
    is preserved as ``__cause__`` so debug consumers can see the full repr.
    """
    assert_canonical_schema(frame)
    for idx, row in enumerate(frame.iter_rows(named=True)):
        row = dict(row)
        for token_field in ("tokens_in_by_model", "tokens_out_by_model"):
            value = row.get(token_field)
            if isinstance(value, dict):
                row[token_field] = {k: v for k, v in value.items() if v is not None}
        try:
            RunRecord.model_validate(row)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else None
            if first is None:
                summary = f"row {idx} violates RunRecord"
            else:
                field_path = ".".join(str(p) for p in first.get("loc", ())) or "<unknown>"
                msg = first.get("msg", "validation failed")
                bad_value = first.get("input", "<n/a>")
                summary = f"row {idx}, field {field_path!r}: value {bad_value!r} — {msg}"
            raise IngestContractError(summary) from exc
