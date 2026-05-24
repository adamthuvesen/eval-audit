"""Adapter for the synthetic known-truth dataset under scouting/synthetic/."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import yaml

from eval_audit.ingest.base import IngestContractError, validate_run_records
from eval_audit.schema.enums import CostProvenance


class SyntheticAdapter:
    """Loads scouting/synthetic/runs.parquet into canonical RunRecord rows."""

    name = "synthetic"

    def load(self, source_path: Path) -> pl.DataFrame:
        source_path = Path(source_path)
        runs_path = source_path / "runs.parquet"
        spec_path = source_path / "spec.yaml"
        if not spec_path.exists():
            raise IngestContractError(
                f"synthetic adapter requires {spec_path.name} next to {runs_path.name}"
            )
        raw = pl.read_parquet(runs_path)

        spec = yaml.safe_load(spec_path.read_text())
        spec_id = spec.get("study", {}).get("id", "synthetic")
        retrieved_at = datetime.fromtimestamp(spec_path.stat().st_mtime, UTC).isoformat()

        # Per-(agent, seed) sum of cost approximates a "run total" for joinability.
        run_totals = raw.group_by(["agent_id", "seed"]).agg(
            pl.col("cost_usd").sum().alias("_run_total")
        )
        joined = raw.join(run_totals, on=["agent_id", "seed"], how="left")

        frame = joined.select(
            pl.col("agent_id"),
            pl.col("agent_id").alias("model_id"),
            pl.lit("synthetic").alias("harness"),
            pl.format("synth-{}-{}", pl.col("agent_id"), pl.col("seed")).alias("run_id"),
            pl.col("task_id"),
            pl.lit(None, dtype=pl.Utf8).alias("task_category"),
            pl.col("seed"),
            pl.col("success").cast(pl.Boolean),
            pl.col("success").cast(pl.Boolean).alias("partial_credit"),
            pl.lit("graded").alias("outcome_status"),
            pl.col("tokens_in"),
            pl.col("tokens_out"),
            pl.col("tokens_in")
            .cast(pl.Int64)
            .map_elements(lambda v: {spec_id: int(v)}, return_dtype=pl.Object)
            .alias("tokens_in_by_model"),
            pl.col("tokens_out")
            .cast(pl.Int64)
            .map_elements(lambda v: {spec_id: int(v)}, return_dtype=pl.Object)
            .alias("tokens_out_by_model"),
            pl.col("wall_clock_s").alias("latency_s"),
            pl.lit(None, dtype=pl.Datetime).alias("timestamp"),
            pl.col("cost_usd").alias("reconstructed_per_task_cost_usd"),
            pl.col("_run_total").alias("reported_run_total_cost_usd"),
            pl.lit(CostProvenance.RECONCILED.value).alias("cost_provenance"),
            pl.lit(
                {
                    "source_fixture": "scouting/synthetic/runs.parquet",
                    "source_retrieved_at": retrieved_at,
                },
                dtype=pl.Object,
            ).alias("rerun_metadata"),
        )

        # Drop the join helper if present (it shouldn't be after select, but be defensive).
        if "_run_total" in frame.columns:
            frame = frame.drop("_run_total")

        self.validate(frame)
        return frame

    def validate(self, frame: pl.DataFrame) -> None:
        validate_run_records(frame)
        if "harness" in frame.columns and not (frame["harness"] == "synthetic").all():
            raise IngestContractError(
                "synthetic adapter expects every row to have harness='synthetic'"
            )
