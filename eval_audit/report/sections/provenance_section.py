"""Provenance section bodies for markdown reports."""

from __future__ import annotations

from pathlib import Path

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
    if run_plan_exists:
        parts.append(f"- **run_plan:** `{run_plan_rel}`")
    if decision_exists:
        parts.append(f"- **decision_doc:** `{decision_rel}`")
    if not runs.is_empty() and "rerun_metadata" in runs.columns:
        first_meta: dict = runs.row(0, named=True)["rerun_metadata"] or {}
        task_source = first_meta.get("task_source")
        harness_commit = first_meta.get("harness_commit")
        rerun_policy = first_meta.get("rerun_policy")
        price_table_date = first_meta.get("price_table_date")
        if task_source:
            parts.append(f"- **task_source:** `{task_source}`")
        harness_line = f"- **harness:** `{study.harness}`"
        if harness_commit and harness_commit != "unknown":
            harness_line += f" at git commit `{harness_commit}`"
        parts.append(harness_line)
        arm_summary = (
            runs.group_by(["agent_id", "model_id"])
            .agg(pl.col("run_id").n_unique().alias("n_runs"))
            .sort("agent_id")
        )
        parts.append("- **model_arms:**")
        for row in arm_summary.iter_rows(named=True):
            parts.append(
                f"  - `{row['agent_id']}` → `{row['model_id']}` "
                f"({row['n_runs']} run(s) per task)"
            )
        if rerun_policy:
            parts.append(f"- **rerun_policy:** `{rerun_policy}`")
        if "timestamp" in runs.columns:
            with_ts = runs.filter(pl.col("timestamp").is_not_null())
            if not with_ts.is_empty():
                ts_min = with_ts["timestamp"].min()
                ts_max = with_ts["timestamp"].max()
                if ts_min == ts_max:
                    parts.append(f"- **run_dates:** `{ts_min.date().isoformat()}` (UTC)")
                else:
                    parts.append(
                        f"- **run_dates:** `{ts_min.date().isoformat()}` to "
                        f"`{ts_max.date().isoformat()}` (UTC)"
                    )
        if price_table_date:
            parts.append(f"- **price_table_pinned_at:** `{price_table_date}`")
    else:
        parts.append(f"- **harness:** `{study.harness}`")
    if "cost_provenance" in runs.columns and not runs.is_empty():
        total = runs.height
        match = runs.filter(
            pl.col("cost_provenance") == presentation.cost_provenance
        ).height
        parts.append(
            f"- **cost_provenance:** `{presentation.cost_provenance}` ({match}/{total} rows)"
        )
    else:
        parts.append(f"- **cost_provenance:** `{presentation.cost_provenance}`")
    parts.append("")
    return parts


def render_public_provenance(presentation: StudyPresentation) -> list[str]:
    parts = ["## Provenance\n"]
    parts.append(f"- **source_fixture:** `{presentation.source_fixture_rel}`")
    parts.append(f"- **source_url:** {presentation.source_url}")
    parts.append(f"- **retrieved_at:** `{presentation.retrieved_at}`")
    parts.append(f"- **price_table_pinned_at:** `{PRICE_TABLE_PINNED_AT}`")
    parts.append(f"- **cost_provenance:** `{presentation.cost_provenance}`")
    parts.append("")
    return parts
