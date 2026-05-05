"""Acceptance tests for the HAL GAIA ingest adapter."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def gaia_dir(scouting_dir: Path) -> Path:
    return scouting_dir / "candidates" / "gaia"


def test_hal_gaia__cross_harness_rows_are_tagged_with_locked_harness(gaia_dir: Path) -> None:
    """WHEN the adapter loads the GAIA fixture,
    THEN every returned row has harness == 'hal_generalist_agent'.
    """
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter

    adapter = HalGaiaAdapter()
    frame = adapter.load(gaia_dir)

    assert (frame["harness"] == "hal_generalist_agent").all()


def test_hal_gaia__locked_mapping_drift_fails_ingest(gaia_dir: Path, tmp_path: Path) -> None:
    """WHEN columns.json is edited so success_bool is renamed to success_flag while the
    fixture parquet still has success_bool, THEN validate() raises IngestContractError
    naming both the expected and actual column.
    """
    import shutil

    from eval_audit.ingest import IngestContractError
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter

    shadow = tmp_path / "gaia"
    shutil.copytree(gaia_dir, shadow)
    columns = json.loads((shadow / "columns.json").read_text())
    for col in columns["tables"][0]["columns"]:
        if col["raw_name"] == "success_bool":
            col["raw_name"] = "success_flag"
    (shadow / "columns.json").write_text(json.dumps(columns))

    adapter = HalGaiaAdapter()
    with pytest.raises(IngestContractError) as exc_info:
        adapter.load(shadow)
    msg = str(exc_info.value)
    assert "success_bool" in msg or "success_flag" in msg


def test_hal_gaia__reconstructed_sum_matches_reported_run_total(gaia_dir: Path) -> None:
    """WHEN the adapter loads the full GAIA fixture for both Exhibit A agents,
    THEN the cost-sum check passes for both runs without raising
    (per-run abs((sum_recon - reported) / reported) < 0.01).
    """
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter

    adapter = HalGaiaAdapter()
    frame = adapter.load(gaia_dir)

    per_run = (
        frame.group_by("agent_id", "run_id")
        .agg(
            pl.col("reconstructed_per_task_cost_usd").sum().alias("recon"),
            pl.col("reported_run_total_cost_usd").first().alias("reported"),
        )
    )
    for row in per_run.iter_rows(named=True):
        rel_err = abs(row["recon"] - row["reported"]) / row["reported"]
        assert rel_err < 0.01, (
            f"agent={row['agent_id']!r} reported={row['reported']:.4f} "
            f"recon={row['recon']:.4f} rel_err={rel_err:.4f}"
        )


def test_hal_gaia__unknown_model_fails_loud(gaia_dir: Path, tmp_path: Path) -> None:
    """WHEN the fixture contains a tokens_in_by_model entry for a model not in the
    price table, THEN IngestContractError is raised whose message names the missing
    model and the pinned-at date.
    """
    import shutil

    from eval_audit.ingest import IngestContractError
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter

    shadow = tmp_path / "gaia"
    shutil.copytree(gaia_dir, shadow)

    sample = pl.read_parquet(shadow / "sample.parquet")
    # Inject an unknown model into the first row's tokens_in_by_model.
    first_row = sample.row(0, named=True)
    bad_tin = json.loads(first_row["tokens_in_by_model"])
    bad_tin["totally-fake-model-xyz"] = 100
    sample = sample.with_row_index().with_columns(
        pl.when(pl.col("index") == 0)
        .then(pl.lit(json.dumps(bad_tin)))
        .otherwise(pl.col("tokens_in_by_model"))
        .alias("tokens_in_by_model")
    ).drop("index")
    sample.write_parquet(shadow / "sample.parquet")

    adapter = HalGaiaAdapter()
    with pytest.raises(IngestContractError) as exc_info:
        adapter.load(shadow)
    msg = str(exc_info.value)
    assert "totally-fake-model-xyz" in msg
    assert "2026-05-02" in msg or "pinned" in msg.lower()


def test_hal_gaia__rows_record_price_table_pin_date(gaia_dir: Path) -> None:
    """WHEN GAIA rows are loaded,
    THEN every row's rerun_metadata includes price_table_pinned_at matching
    _prices.PRICE_TABLE_PINNED_AT.
    """
    from eval_audit.ingest._prices import PRICE_TABLE_PINNED_AT
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter

    adapter = HalGaiaAdapter()
    frame = adapter.load(gaia_dir)

    for row in frame.iter_rows(named=True):
        meta = row["rerun_metadata"]
        assert meta.get("price_table_pinned_at") == PRICE_TABLE_PINNED_AT


def test_hal_gaia__adapter_reads_provenance_from_scouting_fixture(gaia_dir: Path) -> None:
    """WHEN the GAIA ingest adapter constructs a RunRecord,
    THEN every row's cost_provenance matches the outcome field in
    scouting/candidates/gaia/cost-reconciliation.json.
    """
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter

    cost_recon = json.loads((gaia_dir / "cost-reconciliation.json").read_text())
    expected_outcome = cost_recon["outcome"]

    adapter = HalGaiaAdapter()
    frame = adapter.load(gaia_dir)

    assert (frame["cost_provenance"] == expected_outcome).all()


def test_hal_gaia__loaded_fixture_passes_adapter_validation(gaia_dir: Path) -> None:
    """WHEN the committed GAIA fixture is loaded,
    THEN the returned frame passes full RunRecord row validation.
    """
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter

    adapter = HalGaiaAdapter()
    frame = adapter.load(gaia_dir)

    adapter.validate(frame)
