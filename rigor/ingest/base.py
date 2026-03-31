"""Adapter Protocol shared by every benchmark ingest implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import polars as pl

from rigor.schema import RunRecord


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
