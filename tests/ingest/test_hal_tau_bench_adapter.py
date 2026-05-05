"""Acceptance tests for the HAL TAU-bench Tool Calling ingest adapter."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def taubench_dir(scouting_dir: Path) -> Path:
    return scouting_dir / "candidates" / "tau-bench"


_EXPECTED_AGENTS = {
    "Taubench ToolCalling (claude-3.7-sonnet)",
    "Taubench ToolCalling (o3-2025-04-16)",
    "Taubench ToolCalling (o4-mini-2025-04-16 high)",
}


def test_hal_tau_bench__loads_canonical_schema_for_three_agents(taubench_dir: Path) -> None:
    """WHEN HalTauBenchAdapter().load(scouting/candidates/tau-bench) is called,
    THEN the returned frame has 150 rows (3 agents x 50 tasks) with every RunRecord
    field as a column, harness == 'tau_bench_tool_calling' for every row, and
    cost_provenance == 'as_reported_only' for every row.
    """
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
    from eval_audit.schema import RunRecord

    adapter = HalTauBenchAdapter()
    frame = adapter.load(taubench_dir)

    assert frame.height == 150
    assert set(frame["agent_id"].unique().to_list()) == _EXPECTED_AGENTS
    assert (frame["harness"] == "tau_bench_tool_calling").all()
    assert (frame["cost_provenance"] == "as_reported_only").all()

    expected_fields = set(RunRecord.model_fields.keys())
    assert set(frame.columns) == expected_fields


def test_hal_tau_bench__errored_rows_preserved_with_success_none(taubench_dir: Path) -> None:
    """WHEN the adapter loads the Claude rows,
    THEN the 3 rows with raw outcome_status == 'errored' appear in the output with
    success and partial_credit both None, and outcome_status == 'errored' for those rows.
    """
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter

    adapter = HalTauBenchAdapter()
    frame = adapter.load(taubench_dir)

    errored = frame.filter(pl.col("outcome_status") == "errored")
    assert errored.height == 3
    assert (errored["agent_id"] == "Taubench ToolCalling (claude-3.7-sonnet)").all()
    assert errored["success"].null_count() == 3
    assert errored["partial_credit"].null_count() == 3


def test_hal_tau_bench__per_task_cost_reconstruction_not_attempted(taubench_dir: Path) -> None:
    """WHEN any row is loaded by HalTauBenchAdapter,
    THEN reconstructed_per_task_cost_usd is None for that row, AND the row's
    rerun_metadata does NOT include a price_table_pinned_at key.
    """
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter

    adapter = HalTauBenchAdapter()
    frame = adapter.load(taubench_dir)

    assert frame["reconstructed_per_task_cost_usd"].null_count() == frame.height
    for row in frame.iter_rows(named=True):
        assert "price_table_pinned_at" not in row["rerun_metadata"]


def test_hal_tau_bench__outcome_class_drift_fails_ingest(
    taubench_dir: Path, tmp_path: Path
) -> None:
    """WHEN a shadow copy of cost-reconciliation.json is edited so outcome reads
    'reconciled' while the fixture's per-task tokens still don't reconcile,
    THEN the adapter raises IngestContractError naming the unexpected outcome value.
    """
    from eval_audit.ingest import IngestContractError
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter

    shadow = tmp_path / "tau-bench"
    shutil.copytree(taubench_dir, shadow)
    cost_recon = json.loads((shadow / "cost-reconciliation.json").read_text())
    cost_recon["outcome"] = "reconciled"
    (shadow / "cost-reconciliation.json").write_text(json.dumps(cost_recon))

    adapter = HalTauBenchAdapter()
    with pytest.raises(IngestContractError) as exc_info:
        adapter.load(shadow)
    msg = str(exc_info.value)
    assert "reconciled" in msg
    assert "as_reported_only" in msg


def test_hal_tau_bench__run_total_replicated_per_agent_run(taubench_dir: Path) -> None:
    """WHEN the adapter loads the full fixture,
    THEN every row in a given (agent_id, run_id) group carries the same
    reported_run_total_cost_usd, equal to the fixture's run_total_cost_usd for
    that group.
    """
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter

    adapter = HalTauBenchAdapter()
    frame = adapter.load(taubench_dir)

    # One unique reported_run_total_cost_usd per (agent_id, run_id).
    per_run = frame.group_by(["agent_id", "run_id"]).agg(
        pl.col("reported_run_total_cost_usd").n_unique().alias("n_unique")
    )
    assert (per_run["n_unique"] == 1).all()

    # And those values must match the fixture's run_total_cost_usd column.
    raw = pl.read_parquet(taubench_dir / "sample.parquet")
    raw_per_run = raw.group_by(["agent_id", "run_id"]).agg(
        pl.col("run_total_cost_usd").first().alias("expected")
    )
    merged = (
        frame.group_by(["agent_id", "run_id"])
        .agg(pl.col("reported_run_total_cost_usd").first().alias("got"))
        .join(raw_per_run, on=["agent_id", "run_id"])
    )
    for row in merged.iter_rows(named=True):
        assert abs(row["got"] - row["expected"]) < 1e-9


def test_hal_tau_bench__loaded_fixture_passes_adapter_validation(taubench_dir: Path) -> None:
    """WHEN the committed TAU-bench fixture is loaded,
    THEN the returned frame passes full RunRecord row validation.
    """
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter

    adapter = HalTauBenchAdapter()
    frame = adapter.load(taubench_dir)

    adapter.validate(frame)
