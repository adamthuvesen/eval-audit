"""Adapter for the HAL TAU-bench Tool Calling fixture under
scouting/candidates/tau-bench/.

Mirrors HalGaiaAdapter's locked-mapping discipline, but the fixture's
cost-reconciliation outcome is `as_reported_only` (MAPE = 0.33), so per-task
cost reconstruction is NOT performed. `reconstructed_per_task_cost_usd` is
None for every row; downstream consumers must use `reported_run_total_cost_usd`
(replicated to each task row for joinability).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from eval_audit.ingest.base import IngestContractError
from eval_audit.ingest.hal_common import (
    decode_hal_token_counts,
    hal_common_record_fields,
    hal_success_fields,
    load_hal_fixture,
    validate_hal_harness,
)
from eval_audit.schema.enums import CostProvenance

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
_REQUIRED_OUTCOME = CostProvenance.AS_REPORTED_ONLY.value
_EXPECTED_AGENTS = {
    "Taubench ToolCalling (claude-3.7-sonnet)",
    "Taubench ToolCalling (o3-2025-04-16)",
    "Taubench ToolCalling (o4-mini-2025-04-16 high)",
}


class HalTauBenchAdapter:
    """Loads scouting/candidates/tau-bench/sample.parquet into canonical RunRecord rows."""

    name = "hal-tau-bench"

    def load(self, source_path: Path) -> pl.DataFrame:
        raw, cost_recon, provenance = load_hal_fixture(
            source_path,
            locked_mapping=_LOCKED_COLUMN_MAPPING,
        )
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

        retrieved_at = str(provenance.get("retrieved_at", ""))
        rel_fixture = "scouting/candidates/tau-bench/sample.parquet"

        records: list[dict] = []
        for r in raw.iter_rows(named=True):
            tin, tout = decode_hal_token_counts(r)
            success, partial_credit = hal_success_fields(
                r,
                partial_credit_column="reward",
            )

            records.append(
                hal_common_record_fields(
                    r,
                    harness=_HARNESS,
                    success=success,
                    partial_credit=partial_credit,
                    tokens_in_by_model=tin,
                    tokens_out_by_model=tout,
                    reconstructed_cost=None,
                    cost_provenance=outcome,
                    rerun_metadata={
                        "git_commit": str(r.get("git_commit", "")),
                        "source_fixture": rel_fixture,
                        "source_retrieved_at": retrieved_at,
                        "agent_short": str(r.get("agent_short", "")),
                    },
                )
            )

        frame = pl.DataFrame(records, strict=False)
        # Sort defensively: downstream group_by + bootstrap rely on stable ordering.
        frame = frame.sort(["agent_id", "task_id"])
        self.validate(frame)
        return frame

    def validate(self, frame: pl.DataFrame) -> None:
        validate_hal_harness(frame, harness=_HARNESS, adapter_name="hal-tau-bench")
