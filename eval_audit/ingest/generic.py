"""Generic ingest path for canonical RunRecord-shaped parquet files.

Unlike adapters in this package, the generic loader does NOT implement the
``IngestAdapter`` Protocol: adapters take a directory containing auxiliary
files (cost-reconciliation, columns mapping, provenance) for real benchmark
fixtures, while this loader takes a single parquet whose schema already
matches ``RunRecord``. The dual file/directory convention is deliberate and
documented in ``agents/docs/INPUT_CONTRACT.md``.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from eval_audit.ingest.base import validate_run_records


def load_run_records(parquet_path: Path) -> pl.DataFrame:
    """Load a canonical RunRecord-shaped parquet and validate it row-by-row.

    The function reads the parquet via ``polars.read_parquet`` and applies
    the canonical-schema check via :func:`validate_run_records`. No column
    rename, no derived fields, no defaults — input must already be canonical.

    Raises ``IngestContractError`` when the parquet's columns drift from
    ``RunRecord.model_fields`` or when any row violates the canonical
    Pydantic model. The original ``pydantic.ValidationError`` is preserved
    as ``__cause__`` for debug consumers.
    """
    frame = pl.read_parquet(parquet_path)
    validate_run_records(frame)
    return frame
