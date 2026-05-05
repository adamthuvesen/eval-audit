"""Adapter Protocol shared by every benchmark ingest implementation."""

from __future__ import annotations

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
    """Validate every row through the canonical RunRecord Pydantic model."""
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
            raise IngestContractError(f"row {idx} violates RunRecord: {exc}") from exc
