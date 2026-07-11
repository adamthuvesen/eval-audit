"""Provenance section bodies for markdown reports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

import polars as pl

from eval_audit.ingest._prices import PRICE_TABLE_PINNED_AT
from eval_audit.report.presentation import StudyPresentation
from eval_audit.schema import StudySpec


def render_provenance_controlled_evidence(
    study: StudySpec,
    runs: pl.DataFrame,
    repo_root: Path,
    presentation: StudyPresentation,
) -> list[str]:
    parts: list[str] = []
    run_plan_rel = f"scouting/{study.id}/run-plan.md"
    decision_rel = f"scouting/{study.id}-decision.md"
    run_plan_exists = (repo_root / run_plan_rel).exists()
    decision_exists = (repo_root / decision_rel).exists()
    parts.append(
        "- **mode:** `controlled_original_runs` — predeclared run, paired arms on "
        "the same task IDs under one harness; this is original evidence, not "
        "public-data reanalysis or a synthetic example."
    )
    parts.extend(
        _controlled_artifact_lines(run_plan_rel, run_plan_exists, decision_rel, decision_exists)
    )
    if not runs.is_empty() and "rerun_metadata" in runs.columns:
        parts.extend(_controlled_run_metadata_lines(study, runs))
    else:
        parts.append(f"- **harness:** `{study.harness}`")
    parts.append(_controlled_cost_provenance_line(runs, presentation))
    parts.append("")
    return parts


def _controlled_artifact_lines(
    run_plan_rel: str,
    run_plan_exists: bool,
    decision_rel: str,
    decision_exists: bool,
) -> list[str]:
    parts: list[str] = []
    if run_plan_exists:
        parts.append(f"- **run_plan:** `{run_plan_rel}`")
    if decision_exists:
        parts.append(f"- **decision_doc:** `{decision_rel}`")
    return parts


def _controlled_run_metadata_lines(study: StudySpec, runs: pl.DataFrame) -> list[str]:
    first_meta: dict = runs.row(0, named=True)["rerun_metadata"] or {}
    parts: list[str] = []
    if task_source := first_meta.get("task_source"):
        parts.append(f"- **task_source:** `{task_source}`")
    parts.append(_harness_line(study.harness, first_meta.get("harness_commit")))
    parts.extend(_model_arm_lines(runs))
    if rerun_policy := first_meta.get("rerun_policy"):
        parts.append(f"- **rerun_policy:** `{rerun_policy}`")
    if run_dates := _run_dates_line(runs):
        parts.append(run_dates)
    if price_table_date := first_meta.get("price_table_date"):
        parts.append(f"- **price_table_pinned_at:** `{price_table_date}`")
    return parts


def _harness_line(harness: str, harness_commit: object) -> str:
    line = f"- **harness:** `{harness}`"
    if harness_commit and harness_commit != "unknown":
        line += f" at git commit `{harness_commit}`"
    return line


def _model_arm_lines(runs: pl.DataFrame) -> list[str]:
    arm_summary = (
        runs.group_by(["agent_id", "model_id"])
        .agg(pl.col("run_id").n_unique().alias("n_runs"))
        .sort("agent_id")
    )
    parts = ["- **model_arms:**"]
    for row in arm_summary.iter_rows(named=True):
        parts.append(
            f"  - `{row['agent_id']}` → `{row['model_id']}` ({row['n_runs']} run(s) per task)"
        )
    return parts


def _run_dates_line(runs: pl.DataFrame) -> str | None:
    if "timestamp" not in runs.columns:
        return None
    with_ts = runs.filter(pl.col("timestamp").is_not_null())
    if with_ts.is_empty():
        return None
    ts_min = cast(datetime, with_ts["timestamp"].min())
    ts_max = cast(datetime, with_ts["timestamp"].max())
    if ts_min == ts_max:
        return f"- **run_dates:** `{ts_min.date().isoformat()}` (UTC)"
    return f"- **run_dates:** `{ts_min.date().isoformat()}` to `{ts_max.date().isoformat()}` (UTC)"


def _controlled_cost_provenance_line(
    runs: pl.DataFrame,
    presentation: StudyPresentation,
) -> str:
    if "cost_provenance" in runs.columns and not runs.is_empty():
        total = runs.height
        match = runs.filter(pl.col("cost_provenance") == presentation.cost_provenance).height
        return f"- **cost_provenance:** `{presentation.cost_provenance}` ({match}/{total} rows)"
    return f"- **cost_provenance:** `{presentation.cost_provenance}`"


def render_public_provenance(presentation: StudyPresentation) -> list[str]:
    parts = ["## Provenance\n"]
    parts.append(f"- **source_fixture:** `{presentation.source_fixture_rel}`")
    parts.append(f"- **source_url:** {presentation.source_url}")
    parts.append(f"- **retrieved_at:** `{presentation.retrieved_at}`")
    parts.append(f"- **price_table_pinned_at:** `{PRICE_TABLE_PINNED_AT}`")
    parts.append(f"- **cost_provenance:** `{presentation.cost_provenance}`")
    parts.append("")
    return parts
