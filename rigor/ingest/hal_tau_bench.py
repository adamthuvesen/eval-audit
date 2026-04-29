"""Adapter for the HAL TAU-bench Tool Calling fixture under
scouting/candidates/tau-bench/.

Mirrors HalGaiaAdapter's locked-mapping discipline, but the fixture's
cost-reconciliation outcome is `as_reported_only` (MAPE = 0.33), so per-task
cost reconstruction is NOT performed. `reconstructed_per_task_cost_usd` is
None for every row; downstream consumers must use `reported_run_total_cost_usd`
(replicated to each task row for joinability).
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from rigor.ingest.base import IngestContractError, assert_canonical_schema

# Locked column mapping for scouting/candidates/tau-bench/sample.parquet.
# raw_name -> semantic_role for the tau-bench per_task table. The
# `reward` -> `partial_credit` mapping is the only structural difference
# from GAIA (TAU-bench has no `score_raw` column).
_LOCKED_COLUMN_MAPPING: list[tuple[str, str]] = [
    ("agent_id", "agent_id"),
    ("model_id", "model_id"),
    ("run_id", "run_id"),
    ("task_id", "task_id"),
    ("reward", "partial_credit"),
    ("success_bool", "success"),
    ("outcome_status", "outcome_status"),
    ("tokens_in_by_model", "tokens_in_by_model"),
    ("tokens_out_by_model", "tokens_out_by_model"),
    ("tokens_in_total", "tokens_in"),
    ("tokens_out_total", "tokens_out"),
    ("latency_total_s", "latency_s"),
    ("first_call_ts", "timestamp"),
    ("last_call_ts", "timestamp"),
    ("run_total_cost_usd", "cost_usd"),
    ("git_commit", "rerun_metadata"),
]

_HARNESS = "tau_bench_tool_calling"
_REQUIRED_OUTCOME = "as_reported_only"
_EXPECTED_AGENTS = {
    "Taubench ToolCalling (claude-3.7-sonnet)",
    "Taubench ToolCalling (o3-2025-04-16)",
    "Taubench ToolCalling (o4-mini-2025-04-16 high)",
}


def _check_locked_mapping(columns_path: Path, fixture_columns: list[str]) -> None:
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
    for raw_name, semantic_role in _LOCKED_COLUMN_MAPPING:
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


def _decode_token_dict(value: str | None) -> dict[str, int]:
    if value in (None, ""):
        return {}
    decoded = json.loads(value)
    return {str(k): int(v) for k, v in decoded.items()}


class HalTauBenchAdapter:
    """Loads scouting/candidates/tau-bench/sample.parquet into canonical RunRecord rows."""

    name = "hal-tau-bench"

    def load(self, source_path: Path) -> pl.DataFrame:
        source_path = Path(source_path)
        sample_path = source_path / "sample.parquet"
        columns_path = source_path / "columns.json"
        cost_recon_path = source_path / "cost-reconciliation.json"
        provenance_path = source_path / "provenance.json"

        raw = pl.read_parquet(sample_path)
        _check_locked_mapping(columns_path, raw.columns)

        cost_recon = json.loads(cost_recon_path.read_text())
        outcome = cost_recon.get("outcome")
        if outcome != _REQUIRED_OUTCOME:
            raise IngestContractError(
                f"cost-reconciliation.json outcome={outcome!r} is not the locked "
                f"value {_REQUIRED_OUTCOME!r} for the tau-bench fixture"
            )

        agents_in_fixture = set(raw["agent_id"].unique().to_list())
        unexpected = agents_in_fixture - _EXPECTED_AGENTS
        if unexpected:
            raise IngestContractError(
                f"unexpected agent_id values in tau-bench fixture: {sorted(unexpected)}; "
                f"expected one of {sorted(_EXPECTED_AGENTS)}"
            )

        provenance = (
            json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
        )
        retrieved_at = str(provenance.get("retrieved_at", ""))
        rel_fixture = "scouting/candidates/tau-bench/sample.parquet"

        records: list[dict] = []
        for r in raw.iter_rows(named=True):
            tin = _decode_token_dict(r["tokens_in_by_model"])
            tout = _decode_token_dict(r["tokens_out_by_model"])
            is_errored = r["outcome_status"] == "errored"
            success_raw = r["success_bool"]
            success = (
                None
                if is_errored or success_raw is None
                else bool(success_raw)
            )
            partial_credit = None if is_errored else r["reward"]

            records.append({
                "agent_id":           r["agent_id"],
                "model_id":           r["model_id"],
                "harness":            _HARNESS,
                "run_id":             r["run_id"],
                "task_id":            r["task_id"],
                "task_category":      None,
                "seed":               None,
                "success":            success,
                "partial_credit":     partial_credit,
                "outcome_status":     r["outcome_status"],
                "tokens_in":          int(r["tokens_in_total"]),
                "tokens_out":         int(r["tokens_out_total"]),
                "tokens_in_by_model":  tin,
                "tokens_out_by_model": tout,
                "latency_s":          float(r["latency_total_s"]) if r["latency_total_s"] is not None else None,
                "timestamp":          r["first_call_ts"],
                "reconstructed_per_task_cost_usd": None,
                "reported_run_total_cost_usd":     float(r["run_total_cost_usd"]),
                "cost_provenance":    outcome,
                "rerun_metadata": {
                    "git_commit":          str(r.get("git_commit", "")),
                    "source_fixture":      rel_fixture,
                    "source_retrieved_at": retrieved_at,
                    "agent_short":         str(r.get("agent_short", "")),
                },
            })

        frame = pl.DataFrame(records, strict=False)
        # Sort defensively: downstream group_by + bootstrap rely on stable ordering.
        return frame.sort(["agent_id", "task_id"])

    def validate(self, frame: pl.DataFrame) -> None:
        assert_canonical_schema(frame)
        if "harness" in frame.columns and not (frame["harness"] == _HARNESS).all():
            raise IngestContractError(
                f"hal-tau-bench adapter expects every row to have harness={_HARNESS!r}"
            )
