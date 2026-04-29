"""Acceptance tests for the cost-provenance caveat sub-block.

Spec: openspec/changes/exhibit-b-tau-bench-reanalysis/specs/report-rendering/spec.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

FIXED_CLOCK = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)


def _stub_study_for_taubench():
    from rigor.schema import StudySpec

    return StudySpec(
        id="exhibit-b-stub",
        benchmark="tau-bench",
        analysis_mode="declared_reanalysis",
        data_observation="full_seen",
        harness="tau_bench_tool_calling",
        primary_outcome={"name": "success_rate", "unit": "task", "direction": "higher_is_better"},
        agents=[
            {"id": "Taubench ToolCalling (claude-3.7-sonnet)"},
            {"id": "Taubench ToolCalling (o4-mini-2025-04-16 high)"},
        ],
        design={
            "task_sampling": "fixed",
            "run_strategy": "observed",
            "observed_runs_per_agent": 1,
            "rerun_policy": "n/a",
        },
        inference={
            "alpha": 0.05,
            "correction_method": "holm_bonferroni",
            "comparison_family": "declared_claims",
            "target_mde": 0.05,
        },
        cost={
            "metrics": ["reported_run_total_cost_usd", "cost_per_success_usd"],
            "primary_view": "pareto_frontier",
        },
        claims=[
            {
                "id": "claude_vs_o4mini",
                "text": "claude vs o4mini under tool calling",
                "treatment": "Taubench ToolCalling (claude-3.7-sonnet)",
                "control": "Taubench ToolCalling (o4-mini-2025-04-16 high)",
                "outcome": "success_rate",
            }
        ],
    )


def _render_taubench_report(repo_root: Path) -> str:
    from rigor.ingest.hal_tau_bench import HalTauBenchAdapter
    from rigor.report.markdown import render_report
    from rigor.stats import analyze

    study = _stub_study_for_taubench()
    runs = HalTauBenchAdapter().load(repo_root / "scouting" / "candidates" / "tau-bench")
    # Filter to two agents to match the stub study's claim arms.
    runs = runs.filter(
        pl.col("agent_id").is_in([
            "Taubench ToolCalling (claude-3.7-sonnet)",
            "Taubench ToolCalling (o4-mini-2025-04-16 high)",
        ])
    )
    result = analyze(study, runs, bootstrap_iterations=500, bootstrap_seed=42)
    return render_report(
        result,
        study,
        clock=lambda: FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
    )


def test_caveat__as_reported_only_renders_sub_block(repo_root: Path) -> None:
    """WHEN the renderer is called against an analysis result whose fixture has
    cost-reconciliation.json outcome 'as_reported_only' (e.g. tau-bench),
    THEN the rendered report's '## Provenance' section contains a
    '### Cost provenance caveat' sub-block with the warning callout, summary
    paragraph, divergence list, and caveat list, in that order.
    """
    text = _render_taubench_report(repo_root)

    # Sub-block exists.
    assert "### Cost provenance caveat" in text

    # Sections appear in the correct order.
    prov_idx = text.index("## Provenance")
    caveat_idx = text.index("### Cost provenance caveat")
    summary_idx = text.index("## Per-agent summary")
    assert prov_idx < caveat_idx < summary_idx

    # Sub-block opens with the warning callout.
    block = text[caveat_idx:summary_idx]
    assert "> ⚠️ Cost provenance: as_reported_only" in block

    # Each required element appears within the block, in order.
    divergences_idx = block.index("**Divergences (per run):**")
    caveats_idx = block.index("**Caveats:**")
    callout_idx = block.index("> ⚠️ Cost provenance: as_reported_only")
    assert callout_idx < divergences_idx < caveats_idx
