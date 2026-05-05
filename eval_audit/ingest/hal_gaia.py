"""Adapter for the HAL GAIA fixture under scouting/candidates/gaia/.

Inherits the locked column-to-semantic-role mapping from
scouting/gaia-hal-generalist-decision.md verbatim. Per-task cost is reconstructed from
tokens_in_by_model + tokens_out_by_model multiplied by the pinned price table
in `_prices.py`. After loading, the adapter asserts that summed reconstructed
per-task cost matches HAL's reported run total within 1% per (agent, run) —
the contract check that the GAIA fixture remains `reconciled`.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from eval_audit.ingest._prices import PRICE_TABLE, PRICE_TABLE_PINNED_AT
from eval_audit.ingest.base import IngestContractError
from eval_audit.ingest.hal_common import (
    decode_hal_token_counts,
    hal_common_record_fields,
    hal_success_fields,
    load_hal_fixture,
    validate_hal_harness,
)
from eval_audit.schema.enums import CostProvenance

# Locked column mapping from scouting/gaia-hal-generalist-decision.md.
# raw_name -> semantic_role for the GAIA per_task table.
_LOCKED_COLUMN_MAPPING: list[tuple[str, str]] = [
    ("agent_id", "agent_id"),
    ("model_id", "model_id"),
    ("run_id", "run_id"),
    ("task_id", "task_id"),
    ("score_raw", "partial_credit"),
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

_HARNESS = "hal_generalist_agent"
_COST_RECONCILIATION_OUTCOMES = {
    CostProvenance.RECONCILED.value,
    "partial",
    CostProvenance.AS_REPORTED_ONLY.value,
    "not_applicable",
}


def _reconstruct_cost(tin: dict[str, int], tout: dict[str, int]) -> float:
    total = 0.0
    seen: set[str] = set()
    for d in (tin, tout):
        seen.update(d.keys())
    for model in seen:
        if model not in PRICE_TABLE:
            raise IngestContractError(
                f"unknown model {model!r} not in pinned PRICE_TABLE "
                f"(pinned at {PRICE_TABLE_PINNED_AT}); cannot reconstruct cost"
            )
    for model, (in_price, out_price) in PRICE_TABLE.items():
        total += tin.get(model, 0) * in_price / 1_000_000
        total += tout.get(model, 0) * out_price / 1_000_000
    return total


class HalGaiaAdapter:
    """Loads scouting/candidates/gaia/sample.parquet into canonical RunRecord rows."""

    name = "hal-gaia"

    def load(self, source_path: Path) -> pl.DataFrame:
        raw, cost_recon, provenance = load_hal_fixture(
            source_path,
            locked_mapping=_LOCKED_COLUMN_MAPPING,
        )
        outcome = cost_recon.get("outcome")
        if outcome not in _COST_RECONCILIATION_OUTCOMES:
            raise IngestContractError(
                f"cost-reconciliation.json outcome={outcome!r} is not in the canonical "
                f"vocabulary {sorted(_COST_RECONCILIATION_OUTCOMES)}"
            )

        retrieved_at = str(provenance.get("retrieved_at", ""))
        rel_fixture = "scouting/candidates/gaia/sample.parquet"

        # Build canonical rows row-wise (small fixture: 330 rows). We track
        # reconciliation cost (token-derived for ALL rows) separately from the
        # canonical `reconstructed_per_task_cost_usd` field, which nulls
        # errored rows per the errored-row cost policy. Reconciliation must
        # use the full per-task cost — including errored rows — to compare
        # against HAL's reported run total, which bills tokens spent on
        # errored runs.
        records: list[dict] = []
        recon_for_reconciliation: list[float] = []
        for r in raw.iter_rows(named=True):
            tin, tout = decode_hal_token_counts(r)
            full_recon_cost = _reconstruct_cost(tin, tout)
            recon_for_reconciliation.append(full_recon_cost)
            # Errored rows must null success / partial_credit / reconstructed
            # cost (mirror of the TAU-bench adapter pattern). The schema's
            # errored-row invariant rejects non-null success on errored rows;
            # the errored-row cost policy in analyze.py treats errored rows
            # as having no per-task cost contribution.
            success, partial_credit = hal_success_fields(
                r,
                partial_credit_column="score_raw",
            )
            is_errored = r["outcome_status"] == "errored"
            recon_cost = None if is_errored else full_recon_cost

            records.append(
                hal_common_record_fields(
                    r,
                    harness=_HARNESS,
                    success=success,
                    partial_credit=partial_credit,
                    tokens_in_by_model=tin,
                    tokens_out_by_model=tout,
                    reconstructed_cost=recon_cost,
                    cost_provenance=outcome,
                    rerun_metadata={
                        "git_commit": str(r.get("git_commit", "")),
                        "source_fixture": rel_fixture,
                        "source_retrieved_at": retrieved_at,
                        "price_table_pinned_at": PRICE_TABLE_PINNED_AT,
                        "agent_short": str(r.get("agent_short", "")),
                    },
                    # GAIA Level metadata is not exposed in HAL traces (see
                    # scouting/gaia-hal-generalist-decision.md residual risk #2).
                    task_category=None,
                )
            )

        frame = pl.DataFrame(records, strict=False)

        # Reconciliation contract: per (agent, run), the full token-derived
        # reconstructed sum (including errored-row contributions) must match
        # HAL's reported run total within 1%.
        recon_frame = frame.with_columns(
            pl.Series("_full_recon", recon_for_reconciliation).alias("_full_recon")
        )
        per_run = (
            recon_frame.group_by("agent_id", "run_id")
            .agg(
                pl.col("_full_recon").sum().alias("_recon"),
                pl.col("reported_run_total_cost_usd").first().alias("_reported"),
            )
        )
        for row in per_run.iter_rows(named=True):
            reported = row["_reported"]
            recon = row["_recon"]
            if reported == 0:
                continue
            rel = abs(recon - reported) / reported
            if rel >= 0.01:
                raise IngestContractError(
                    f"cost reconciliation drift for agent={row['agent_id']!r} "
                    f"run_id={row['run_id']!r}: reported={reported:.4f} "
                    f"reconstructed={recon:.4f} relative_error={rel:.4f} (threshold 0.01)"
                )

        self.validate(frame)
        return frame

    def validate(self, frame: pl.DataFrame) -> None:
        validate_hal_harness(frame, harness=_HARNESS, adapter_name="hal-gaia")
