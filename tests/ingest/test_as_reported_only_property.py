"""Property tests for the as_reported_only cost-provenance path.

Spec: openspec/changes/exhibit-b-tau-bench-reanalysis/tasks.md §7.1
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from rigor.report.markdown import render_report
from rigor.schema import RunRecord, StudySpec
from rigor.stats import analyze

_FIXED_CLOCK = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
_TAUBENCH_DIR = Path(__file__).resolve().parents[2] / "scouting" / "candidates" / "tau-bench"
_REPO_ROOT = Path(__file__).resolve().parents[2]


@given(
    n_graded=st.integers(min_value=2, max_value=20),
    n_errored=st.integers(min_value=0, max_value=5),
    reported_total=st.floats(min_value=0.10, max_value=100.0, allow_nan=False),
)
@settings(max_examples=25, deadline=None)
def test_as_reported_only__run_record_accepts_none_reconstructed_cost(
    n_graded: int, n_errored: int, reported_total: float
) -> None:
    """Generated frames with cost_provenance='as_reported_only' must validate via
    RunRecord with reconstructed_per_task_cost_usd=None for every row.
    """
    for i in range(n_graded):
        RunRecord(
            agent_id="a",
            model_id="m",
            harness="h",
            run_id="r",
            task_id=f"t{i}",
            success=(i % 2 == 0),
            outcome_status="graded",
            tokens_in=1,
            tokens_out=1,
            tokens_in_by_model={"m": 1},
            tokens_out_by_model={"m": 1},
            reconstructed_per_task_cost_usd=None,
            reported_run_total_cost_usd=reported_total,
            cost_provenance="as_reported_only",
            rerun_metadata={},
        )
    for i in range(n_errored):
        RunRecord(
            agent_id="a",
            model_id="m",
            harness="h",
            run_id="r",
            task_id=f"e{i}",
            success=None,
            outcome_status="errored",
            tokens_in=1,
            tokens_out=1,
            tokens_in_by_model={"m": 1},
            tokens_out_by_model={"m": 1},
            reconstructed_per_task_cost_usd=None,
            reported_run_total_cost_usd=reported_total,
            cost_provenance="as_reported_only",
            rerun_metadata={},
        )


def test_as_reported_only__renderer_emits_caveat_block_and_omits_price_pin_metadata() -> None:
    """The TAU-bench fixture's renderer output must contain the caveat sub-block
    and must NOT include any price_table_pinned_at key in any row's rerun_metadata.
    """
    from rigor.ingest.hal_tau_bench import HalTauBenchAdapter

    runs = HalTauBenchAdapter().load(_TAUBENCH_DIR)

    for row in runs.iter_rows(named=True):
        assert "price_table_pinned_at" not in row["rerun_metadata"]

    # Use a stub two-agent study so analyze() runs cleanly.
    study = StudySpec(
        id="exhibit-b-prop",
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
        cost={"metrics": ["cost_per_success_usd"], "primary_view": "pareto_frontier"},
        claims=[
            {
                "id": "c1",
                "text": "claude vs o4mini",
                "treatment": "Taubench ToolCalling (claude-3.7-sonnet)",
                "control": "Taubench ToolCalling (o4-mini-2025-04-16 high)",
                "outcome": "success_rate",
            }
        ],
    )
    runs_two = runs.filter(
        pl.col("agent_id").is_in([
            "Taubench ToolCalling (claude-3.7-sonnet)",
            "Taubench ToolCalling (o4-mini-2025-04-16 high)",
        ])
    )
    result = analyze(study, runs_two, bootstrap_iterations=200, bootstrap_seed=42)
    text = render_report(
        result,
        study,
        clock=lambda: _FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=_REPO_ROOT,
    )
    assert "### Cost provenance caveat" in text
    assert "> ⚠️ Cost provenance: as_reported_only" in text
