"""Tests for the generic RunRecord-shaped parquet loader."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from pydantic import ValidationError

from eval_audit.ingest import IngestContractError, load_run_records
from eval_audit.schema import RunRecord


def test_generic_loader__example_fixture_validates_cleanly(repo_root: Path) -> None:
    """The committed BYO example parquet validates and returns a 20-row frame."""
    frame = load_run_records(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    assert frame.height == 20
    assert set(frame.columns) == set(RunRecord.model_fields.keys())


def test_generic_loader__missing_column_names_the_column(repo_root: Path, tmp_path: Path) -> None:
    """Drop a required column → IngestContractError mentions it by name."""
    src = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    bad = src.drop("cost_provenance")
    bad_path = tmp_path / "missing-col.parquet"
    bad.write_parquet(bad_path)

    with pytest.raises(IngestContractError) as exc_info:
        load_run_records(bad_path)
    assert "cost_provenance" in str(exc_info.value)


def test_generic_loader__bad_enum_value_names_row_and_field(
    repo_root: Path, tmp_path: Path
) -> None:
    """Inject `cost_provenance="wrong"` at row index 3 → error names the row+field."""
    src = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    rows = src.to_dicts()
    rows[3]["cost_provenance"] = "wrong"
    bad = pl.DataFrame(rows, strict=False)
    bad_path = tmp_path / "bad-enum.parquet"
    bad.write_parquet(bad_path)

    with pytest.raises(IngestContractError) as exc_info:
        load_run_records(bad_path)
    msg = str(exc_info.value)
    assert "row 3" in msg
    assert "cost_provenance" in msg
    # Original ValidationError preserved as __cause__ for debug consumers.
    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_generic_loader__byo_example_feeds_analyze_end_to_end(repo_root: Path) -> None:
    """The BYO example parquet flows through analyze() and produces a sane verdict."""
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "examples" / "byo-minimal" / "study.yaml")
    runs = load_run_records(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    result = analyze(study, runs, bootstrap_iterations=1_000, bootstrap_seed=42)

    # alice 0.80 vs bob 0.40 — the delta is unambiguous.
    by_id = {s.agent_id: s for s in result.per_agent}
    assert by_id["alice"].success_rate == 0.8
    assert by_id["bob"].success_rate == 0.4
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.delta_point_estimate == pytest.approx(0.4, abs=1e-9)
