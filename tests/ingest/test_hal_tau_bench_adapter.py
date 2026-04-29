"""Acceptance tests for the HAL TAU-bench Tool Calling ingest adapter.

Spec: openspec/changes/exhibit-b-tau-bench-reanalysis/specs/data-ingest/spec.md
"""

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
    from rigor.ingest.hal_tau_bench import HalTauBenchAdapter
    from rigor.schema import RunRecord

    adapter = HalTauBenchAdapter()
    frame = adapter.load(taubench_dir)

    assert frame.height == 150
    assert set(frame["agent_id"].unique().to_list()) == _EXPECTED_AGENTS
    assert (frame["harness"] == "tau_bench_tool_calling").all()
    assert (frame["cost_provenance"] == "as_reported_only").all()

    expected_fields = set(RunRecord.model_fields.keys())
    assert set(frame.columns) == expected_fields
