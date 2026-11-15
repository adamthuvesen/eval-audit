"""Normalize HumanEval Direct Completion graded outputs into the canonical RunRecord parquet.

Reads ``scouting/humaneval-direct-completion/graded/<agent_short>/<task_id>/<run_id>.json``
(produced by ``grade.py``), reconstructs per-task cost from
``price-table.yaml``, and writes ``examples/humaneval-direct-completion/runs.parquet`` with the
canonical column set used by the BYO loader.

Cost provenance: every row carries ``cost_provenance="partial"``. The
Anthropic Messages API does not expose an independent provider-side run
total, so reconciliation is impossible by construction:
``reconstructed_per_task_cost_usd`` is the per-call cost reconstructed from
API-reported tokens × the pinned price table, and
``reported_run_total_cost_usd`` is the per-(agent, run) sum of those same
per-call costs (not a provider total). ``partial`` is the honest label:
we have one side of the reconciliation, not both.

Usage:

    uv run python scouting/humaneval-direct-completion/normalize.py
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from eval_audit.ingest.base import validate_run_records
from eval_audit.schema import RunRecord

HERE = Path(__file__).resolve().parent
GRADED_DIR = HERE / "graded"
PRICE_TABLE_PATH = HERE / "price-table.yaml"
OUT_PATH = HERE.parent.parent / "examples" / "humaneval-direct-completion" / "runs.parquet"
TASK_ID_RE = re.compile(r"^HumanEval/(\d+)$")
HARNESS_ID = "eval-audit/humaneval-direct-completion-v1"


def _per_call_cost_usd(tokens_in: int, tokens_out: int, rates: dict[str, Any]) -> float:
    return (
        tokens_in * rates["input_per_mtok"] / 1_000_000
        + tokens_out * rates["output_per_mtok"] / 1_000_000
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-evidence-change", action="store_true")
    args = parser.parse_args()
    if not GRADED_DIR.exists():
        raise SystemExit(f"missing graded dir: {GRADED_DIR}; run grade.py first.")
    price_table = yaml.safe_load(PRICE_TABLE_PATH.read_text())
    rates_by_model = price_table["models"]

    files = sorted(GRADED_DIR.rglob("*.json"))
    if not files:
        raise SystemExit(f"no graded outputs under {GRADED_DIR}.")

    rows: list[dict[str, Any]] = []
    for path in files:
        record = json.loads(path.read_text())
        agent_id = record["agent_id"]
        model_id = record["model_id"]
        task_id = record["task_id"]
        run_id = record["run_id"]
        agent_short = record["agent_short"]
        outcome_status = record["outcome_status"]
        success = record.get("success")

        payload = record.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("usage"), dict):
            raise ValueError(f"{path}: missing provider usage, token counts are unknown")
        usage = payload["usage"]
        for field in ("input_tokens", "output_tokens"):
            value = usage.get(field)
            if type(value) is not int or value < 0:
                raise ValueError(f"{path}: {field} must be an explicit non-negative integer")
        for field in ("cache_creation_input_tokens", "cache_read_input_tokens"):
            value = usage.get(field, 0)
            if type(value) is not int or value < 0:
                raise ValueError(f"{path}: {field} must be a non-negative integer when present")
        usage_in_total = (
            usage["input_tokens"]
            + usage.get("cache_creation_input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
        )
        usage_out_total = usage["output_tokens"]
        if outcome_status == "graded" and not record.get("grader", {}).get("check_completed"):
            raise ValueError(
                f"{path}: historical grade has no completion receipt. "
                "Preserve recorded evidence until isolated regrading is available."
            )

        rates = rates_by_model[model_id]
        per_call_cost = _per_call_cost_usd(
            tokens_in=usage_in_total, tokens_out=usage_out_total, rates=rates
        )
        # See module docstring: provenance is "partial" because the Anthropic
        # Messages API does not expose an independent provider-side run total.
        # Errored rows still null reconstructed_cost per the errored-row policy.
        cost_provenance = "partial"
        reconstructed_cost = per_call_cost if outcome_status == "graded" else None

        started_at = record.get("started_at")
        if not isinstance(started_at, str) or not started_at:
            raise ValueError(f"{path}: missing started_at timestamp")
        try:
            timestamp = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{path}: invalid started_at timestamp") from exc
        if timestamp.tzinfo is None:
            raise ValueError(f"{path}: started_at must include a timezone")

        partial_credit: float | None = (
            None if outcome_status == "errored" else (1.0 if success else 0.0)
        )

        m = TASK_ID_RE.match(task_id)
        task_index = int(m.group(1)) if m else None

        rerun_metadata = {
            "harness": HARNESS_ID,
            "harness_commit": str(record.get("harness_commit", "unknown")),
            "system_prompt_sha": _sha8(record["system_prompt"]),
            "temperature": str(record["temperature"]),
            "max_tokens": str(record["max_tokens"]),
            "agent_short": agent_short,
            "rerun_index": run_id.rsplit("-", 1)[-1],
            "rerun_policy": "capture_provider_nondeterminism",
            "task_source": "openai/human-eval (MIT)",
            "price_table_date": str(price_table["date"]),
        }
        if outcome_status == "errored":
            rerun_metadata["error_detail_tail"] = record.get("grader", {}).get("detail", "")[:200]

        rows.append(
            {
                "agent_id": agent_id,
                "model_id": model_id,
                "harness": HARNESS_ID,
                "run_id": run_id,
                "task_id": task_id,
                "task_category": f"humaneval_idx_{task_index:03d}"
                if task_index is not None
                else None,
                "seed": None,
                "success": success,
                "partial_credit": partial_credit,
                "outcome_status": outcome_status,
                "tokens_in": usage_in_total,
                "tokens_out": usage_out_total,
                "tokens_in_by_model": {model_id: usage_in_total},
                "tokens_out_by_model": {model_id: usage_out_total},
                "latency_s": record.get("latency_s"),
                "timestamp": timestamp,
                "reconstructed_per_task_cost_usd": reconstructed_cost,
                "reported_run_total_cost_usd": None,  # filled in pass 2 below
                "cost_provenance": cost_provenance,
                "rerun_metadata": rerun_metadata,
                "_per_call_cost_for_total": per_call_cost,
            }
        )

    df = pl.DataFrame(rows, strict=False)
    totals = df.group_by(["agent_id", "run_id"]).agg(
        pl.col("_per_call_cost_for_total").sum().alias("_run_total")
    )
    df = df.join(totals, on=["agent_id", "run_id"], how="left")
    df = df.with_columns(pl.col("_run_total").alias("reported_run_total_cost_usd")).drop(
        ["_per_call_cost_for_total", "_run_total"]
    )

    df = df.select(list(RunRecord.model_fields))
    validate_run_records(df)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".normalize-", dir=OUT_PATH.parent) as temporary:
        stage = Path(temporary) / "runs.parquet"
        df.write_parquet(stage)
        validate_run_records(pl.read_parquet(stage))
        if (
            OUT_PATH.exists()
            and stage.read_bytes() != OUT_PATH.read_bytes()
            and not args.accept_evidence_change
        ):
            raise ValueError(
                "normalized fixture differs from existing evidence. "
                "Use --accept-evidence-change and review affected reports."
            )
        stage.replace(OUT_PATH)
    print(
        f"wrote {OUT_PATH} ({df.height} rows, "
        f"{df.filter(pl.col('outcome_status') == 'graded').height} graded, "
        f"{df.filter(pl.col('outcome_status') == 'errored').height} errored)"
    )


def _sha8(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode()).hexdigest()[:16]


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        RuntimeError,
        OSError,
        KeyError,
        TypeError,
        yaml.YAMLError,
        pl.exceptions.PolarsError,
    ) as exc:
        import sys

        print(f"normalization failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
