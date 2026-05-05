"""Adapter for the HAL GAIA fixture under scouting/candidates/gaia/.

Inherits the locked column-to-semantic-role mapping from
scouting/exhibit-a-decision.md verbatim. Per-task cost is reconstructed from
tokens_in_by_model + tokens_out_by_model multiplied by the pinned price table
in `_prices.py`. After loading, the adapter asserts that summed reconstructed
per-task cost matches HAL's reported run total within 1% per (agent, run) —
the contract check that the GAIA fixture remains `reconciled`.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from eval_audit.ingest._prices import PRICE_TABLE, PRICE_TABLE_PINNED_AT
from eval_audit.ingest.base import IngestContractError, validate_run_records

# Locked column mapping from scouting/exhibit-a-decision.md.
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
_COST_RECONCILIATION_OUTCOMES = {"reconciled", "partial", "as_reported_only", "not_applicable"}


def _check_locked_mapping(columns_path: Path, fixture_columns: list[str]) -> None:
    """Verify columns.json declares every locked (raw_name, semantic_role) pair AND
    that the parquet fixture exposes every raw_name. Raise on either drift.
    """
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
        source_path = Path(source_path)
        sample_path = source_path / "sample.parquet"
        columns_path = source_path / "columns.json"
        cost_recon_path = source_path / "cost-reconciliation.json"
        provenance_path = source_path / "provenance.json"

        raw = pl.read_parquet(sample_path)
        _check_locked_mapping(columns_path, raw.columns)

        cost_recon = json.loads(cost_recon_path.read_text())
        outcome = cost_recon.get("outcome")
        if outcome not in _COST_RECONCILIATION_OUTCOMES:
            raise IngestContractError(
                f"cost-reconciliation.json outcome={outcome!r} is not in the canonical "
                f"vocabulary {sorted(_COST_RECONCILIATION_OUTCOMES)}"
            )

        provenance = (
            json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
        )
        retrieved_at = str(provenance.get("retrieved_at", ""))
        rel_fixture = "scouting/candidates/gaia/sample.parquet"

        # Build canonical rows row-wise (small fixture: 330 rows).
        records: list[dict] = []
        for r in raw.iter_rows(named=True):
            tin = _decode_token_dict(r["tokens_in_by_model"])
            tout = _decode_token_dict(r["tokens_out_by_model"])
            recon_cost = _reconstruct_cost(tin, tout)

            records.append({
                "agent_id":           r["agent_id"],
                "model_id":           r["model_id"],
                "harness":            _HARNESS,
                "run_id":             r["run_id"],
                "task_id":            r["task_id"],
                # GAIA Level metadata is not exposed in HAL traces (see
                # scouting/exhibit-a-decision.md residual risk #2).
                "task_category":      None,
                # GAIA exposes one run per (agent, model) — no seed metadata.
                "seed":               None,
                "success":            bool(r["success_bool"]) if r["success_bool"] is not None else None,
                "partial_credit":     r["score_raw"],
                "outcome_status":     r["outcome_status"],
                "tokens_in":          int(r["tokens_in_total"]),
                "tokens_out":         int(r["tokens_out_total"]),
                "tokens_in_by_model":  tin,
                "tokens_out_by_model": tout,
                "latency_s":          float(r["latency_total_s"]) if r["latency_total_s"] is not None else None,
                # `first_call_ts` is the locked timestamp source per the column mapping.
                "timestamp":          r["first_call_ts"],
                "reconstructed_per_task_cost_usd": recon_cost,
                "reported_run_total_cost_usd":     float(r["run_total_cost_usd"]),
                "cost_provenance":    outcome,
                "rerun_metadata": {
                    "git_commit":             str(r.get("git_commit", "")),
                    "source_fixture":         rel_fixture,
                    "source_retrieved_at":    retrieved_at,
                    "price_table_pinned_at":  PRICE_TABLE_PINNED_AT,
                    "agent_short":            str(r.get("agent_short", "")),
                },
            })

        frame = pl.DataFrame(records, strict=False)

        # Reconciliation contract: per (agent, run), reconstructed sum must match
        # HAL's reported run total within 1%.
        per_run = (
            frame.group_by("agent_id", "run_id")
            .agg(
                pl.col("reconstructed_per_task_cost_usd").sum().alias("_recon"),
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
        validate_run_records(frame)
        if "harness" in frame.columns and not (frame["harness"] == _HARNESS).all():
            raise IngestContractError(
                f"hal-gaia adapter expects every row to have harness={_HARNESS!r}"
            )
