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


def test_adapter__validate_raises_on_invalid_outcome_status(scouting_dir: Path) -> None:
    """WHEN validate() sees a canonical frame with an invalid outcome_status value,
    THEN IngestContractError names outcome_status.
    """
    import polars as pl
    import pytest

    from rigor.ingest import IngestContractError
    from rigor.ingest.synthetic import SyntheticAdapter

    adapter = SyntheticAdapter()
    frame = (
        adapter.load(scouting_dir / "synthetic")
        .with_row_index()
        .with_columns(
            pl.when(pl.col("index") == 0)
            .then(pl.lit("GRADED"))
            .otherwise(pl.col("outcome_status"))
            .alias("outcome_status")
        )
        .drop("index")
    )

    with pytest.raises(IngestContractError) as exc_info:
        adapter.validate(frame)

    assert "outcome_status" in str(exc_info.value)


def test_adapter__validate_raises_on_graded_row_without_success(scouting_dir: Path) -> None:
    """WHEN validate() sees a graded row with success=None,
    THEN IngestContractError names both success and outcome_status.
    """
    import polars as pl
    import pytest

    from rigor.ingest import IngestContractError
    from rigor.ingest.synthetic import SyntheticAdapter

    adapter = SyntheticAdapter()
    frame = (
        adapter.load(scouting_dir / "synthetic")
        .with_row_index()
        .with_columns(
            pl.when(pl.col("index") == 0)
            .then(pl.lit(None, dtype=pl.Boolean))
            .otherwise(pl.col("success"))
            .alias("success")
        )
        .drop("index")
    )

    with pytest.raises(IngestContractError) as exc_info:
        adapter.validate(frame)

    msg = str(exc_info.value)
    assert "success" in msg
    assert "outcome_status" in msg
