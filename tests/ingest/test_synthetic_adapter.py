"""Acceptance tests for the synthetic ingest adapter."""

from __future__ import annotations

from pathlib import Path


def test_synthetic_adapter__loads_into_canonical_schema(scouting_dir: Path) -> None:
    """WHEN the synthetic adapter's load() is called against the committed runs.parquet,
    THEN the returned frame has every RunRecord field as a column, with
    harness == 'synthetic' for every row and a row count equal to agents x tasks x seeds.
    """
    from rigor.ingest.synthetic import SyntheticAdapter
    from rigor.schema import RunRecord

    adapter = SyntheticAdapter()
    frame = adapter.load(scouting_dir / "synthetic")

    expected_cols = set(RunRecord.model_fields.keys())
    assert set(frame.columns) == expected_cols, (
        f"missing={expected_cols - set(frame.columns)}, extra={set(frame.columns) - expected_cols}"
    )
    assert frame.height == 4 * 60 * 5
    assert (frame["harness"] == "synthetic").all()


def test_adapter__validate_raises_on_column_drift(scouting_dir: Path) -> None:
    """WHEN validate() is called on a frame that is missing the cost_provenance column,
    THEN an IngestContractError is raised whose message names the missing column.
    """
    import polars as pl
    import pytest

    from rigor.ingest import IngestContractError
    from rigor.ingest.synthetic import SyntheticAdapter

    adapter = SyntheticAdapter()
    frame = adapter.load(scouting_dir / "synthetic").drop("cost_provenance")

    with pytest.raises(IngestContractError) as exc_info:
        adapter.validate(frame)

    assert "cost_provenance" in str(exc_info.value)
    # Sanity check: frame is a polars frame so we exercised the realistic code path.
    assert isinstance(frame, pl.DataFrame)
