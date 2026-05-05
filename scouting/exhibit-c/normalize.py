"""Normalize Exhibit C graded outputs into the canonical RunRecord parquet.

Reads ``scouting/exhibit-c/graded/<agent_short>/<task_id>/<run_id>.json``
(produced by ``grade.py``), reconstructs per-task cost from
``price-table.yaml``, and writes ``examples/exhibit-c/runs.parquet`` with the
canonical column set used by the BYO loader.

Cost provenance: every row carries ``cost_provenance="partial"``. The
Anthropic Messages API does not expose an independent provider-side run
total, so reconciliation is impossible by construction:
``reconstructed_per_task_cost_usd`` is the per-call cost reconstructed from
API-reported tokens × the pinned price table, and
``reported_run_total_cost_usd`` is the per-(agent, run) sum of those same
per-call costs (not a provider total). ``partial`` is the honest label —
we have one side of the reconciliation, not both. The
``reconciliation_tolerance_usd`` field in ``price-table.yaml`` is unused
in v0; retained for forward compatibility with a future provider that
exposes a billing total.

Usage:

    uv run python scouting/exhibit-c/normalize.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import polars as pl
import yaml

HERE = Path(__file__).resolve().parent
GRADED_DIR = HERE / "graded"
PRICE_TABLE_PATH = HERE / "price-table.yaml"
OUT_PATH = (
    HERE.parent.parent / "examples" / "exhibit-c" / "runs.parquet"
)
TASK_ID_RE = re.compile(r"^HumanEval/(\d+)$")


def _short(model_id: str) -> str:
    if "haiku" in model_id:
        return "haiku45"
    if "sonnet" in model_id:
        return "sonnet46"
    raise ValueError(f"unrecognized model_id: {model_id}")


def _per_call_cost_usd(
    tokens_in: int, tokens_out: int, rates: dict
) -> float:
    return (
        tokens_in * rates["input_per_mtok"] / 1_000_000
        + tokens_out * rates["output_per_mtok"] / 1_000_000
    )


def main() -> None:
    if not GRADED_DIR.exists():
        raise SystemExit(f"missing graded dir: {GRADED_DIR}; run grade.py first.")
    price_table = yaml.safe_load(PRICE_TABLE_PATH.read_text())
    tolerance = float(price_table.get("reconciliation_tolerance_usd", 0.005))
    rates_by_model = price_table["models"]

    files = sorted(GRADED_DIR.rglob("*.json"))
    if not files:
        raise SystemExit(f"no graded outputs under {GRADED_DIR}.")

    rows: list[dict] = []
    for path in files:
        record = json.loads(path.read_text())
        agent_id = record["agent_id"]
        model_id = record["model_id"]
        task_id = record["task_id"]
        run_id = record["run_id"]
        agent_short = record["agent_short"]
        outcome_status = record["outcome_status"]
        success = record.get("success")

        usage_in = 0
        usage_out = 0
        usage_in_total = 0
        usage_out_total = 0
        if record.get("ok") and isinstance(record.get("payload"), dict):
            usage = record["payload"].get("usage", {}) or {}
            usage_in = int(usage.get("input_tokens") or 0)
            usage_out = int(usage.get("output_tokens") or 0)
            usage_in_total = (
                usage_in
                + int(usage.get("cache_creation_input_tokens") or 0)
                + int(usage.get("cache_read_input_tokens") or 0)
            )
            usage_out_total = usage_out

        rates = rates_by_model[model_id]
        per_call_cost = _per_call_cost_usd(
            tokens_in=usage_in_total, tokens_out=usage_out_total, rates=rates
        )
        # See module docstring: provenance is "partial" because the Anthropic
        # Messages API does not expose an independent provider-side run total.
        # Errored rows still null reconstructed_cost per the errored-row policy.
        cost_provenance = "partial"
        reconstructed_cost = per_call_cost if outcome_status == "graded" else None

        timestamp = None
        if record.get("started_at"):
            try:
                timestamp = datetime.fromisoformat(
                    record["started_at"].replace("Z", "+00:00")
                )
            except ValueError:
                timestamp = None

        partial_credit: float | None = (
            None if outcome_status == "errored" else (1.0 if success else 0.0)
        )

        m = TASK_ID_RE.match(task_id)
        task_index = int(m.group(1)) if m else None

        rerun_metadata = {
            "harness": record["harness"],
            "harness_commit": str(record.get("harness_commit", "unknown")),
            "system_prompt_sha": _sha8(record["system_prompt"]),
            "temperature": str(record["temperature"]),
            "max_tokens": str(record["max_tokens"]),
            "agent_short": agent_short,
            "rerun_index": run_id.rsplit("-", 1)[-1],
            "rerun_policy": "capture_provider_nondeterminism",
            "task_source": "openai/human-eval (MIT)",
            "price_table_date": str(price_table["date"]),
            "reconciliation_tolerance_usd": f"{tolerance:.4f}",
        }
        if outcome_status == "errored":
            rerun_metadata["error_detail_tail"] = (
                record.get("grader", {}).get("detail", "")[:200]
            )

        rows.append(
            {
                "agent_id": agent_id,
                "model_id": model_id,
                "harness": record["harness"],
                "run_id": run_id,
                "task_id": task_id,
                "task_category": f"humaneval_idx_{task_index:03d}" if task_index is not None else None,
                "seed": None,
                "success": success,
                "partial_credit": partial_credit,
                "outcome_status": outcome_status,
                "tokens_in": usage_in_total,
                "tokens_out": usage_out_total,
                "tokens_in_by_model": {model_id: usage_in_total},
                "tokens_out_by_model": {model_id: usage_out_total},
                "latency_s": float(record.get("latency_s") or 0.0),
                "timestamp": timestamp,
                "reconstructed_per_task_cost_usd": reconstructed_cost,
                "reported_run_total_cost_usd": None,  # filled in pass 2 below
                "cost_provenance": cost_provenance,
                "rerun_metadata": rerun_metadata,
                "_per_call_cost_for_total": per_call_cost,
            }
        )

    df = pl.DataFrame(rows, strict=False)
    totals = (
        df.group_by(["agent_id", "run_id"])
        .agg(pl.col("_per_call_cost_for_total").sum().alias("_run_total"))
    )
    df = df.join(totals, on=["agent_id", "run_id"], how="left")
    df = df.with_columns(
        pl.col("_run_total").alias("reported_run_total_cost_usd")
    ).drop(["_per_call_cost_for_total", "_run_total"])

    canonical_cols = [
        "agent_id",
        "model_id",
        "harness",
        "run_id",
        "task_id",
        "task_category",
        "seed",
        "success",
        "partial_credit",
        "outcome_status",
        "tokens_in",
        "tokens_out",
        "tokens_in_by_model",
        "tokens_out_by_model",
        "latency_s",
        "timestamp",
        "reconstructed_per_task_cost_usd",
        "reported_run_total_cost_usd",
        "cost_provenance",
        "rerun_metadata",
    ]
    df = df.select(canonical_cols)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(OUT_PATH)
    print(
        f"wrote {OUT_PATH} ({df.height} rows, "
        f"{df.filter(pl.col('outcome_status') == 'graded').height} graded, "
        f"{df.filter(pl.col('outcome_status') == 'errored').height} errored)"
    )


def _sha8(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode()).hexdigest()[:16]


if __name__ == "__main__":
    main()
