"""Acceptance tests for the cost-provenance caveat sub-block."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

FIXED_CLOCK = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)


def _stub_study_for_taubench():
    from eval_audit.schema import StudySpec

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
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.stats import analyze

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
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
        bootstrap_iterations=500,
        bootstrap_seed=42,
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


def test_caveat__reconciled_fixture_omits_sub_block(repo_root: Path) -> None:
    """WHEN the renderer is called against the GAIA fixture (outcome == 'reconciled'),
    THEN the rendered report's '## Provenance' section does NOT contain a
    '### Cost provenance caveat' sub-block, and Exhibit A's existing snapshot is
    unchanged byte-for-byte.
    """
    import os

    from eval_audit.ingest.hal_gaia import HalGaiaAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")
    runs = HalGaiaAdapter().load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    rendered = render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
        bootstrap_iterations=2_000,
        bootstrap_seed=42,
    )

    assert "### Cost provenance caveat" not in rendered
    assert "as_reported_only" not in rendered
    assert "> ⚠️" not in rendered

    # Snapshot byte-equality (the cross-check asked for in the spec).
    snapshot_path = (
        repo_root / "tests" / "report_snapshots" / "exhibit-a-report.md"
    )
    if os.getenv("UPDATE_SNAPSHOTS") != "1":
        expected = snapshot_path.read_text()
        assert rendered == expected


def test_caveat__cost_per_success_fallback_for_as_reported_only(repo_root: Path) -> None:
    """WHEN the per-agent summary is rendered for a TAU-bench agent under
    as_reported_only, THEN the agent's cost_per_success_usd value equals
    reported_run_total_cost_usd / successes (rounded to currency precision),
    AND a single cost_per_success_usd column header is used (no _reported suffix).
    """
    text = _render_taubench_report(repo_root)
    # Single column header with no _reported suffix.
    assert "| cost_per_success_usd |" in text
    assert "cost_per_success_usd_reported" not in text

    # For Claude: reported_run_total = 15.4455; 22 graded successes; 15.4455/22 = $0.70.
    # Find the per-agent summary table row (table rows start with "| ").
    table_start = text.index("## Per-agent summary")
    table_end = text.index("## Claims")
    table_block = text[table_start:table_end]
    claude_line_start = table_block.index("| Taubench ToolCalling (claude-3.7-sonnet)")
    claude_line_end = table_block.index("\n", claude_line_start)
    claude_line = table_block[claude_line_start:claude_line_end]
    assert "$0.70" in claude_line


def test_caveat__divergences_surfaced_verbatim(repo_root: Path) -> None:
    """WHEN the caveat sub-block renders divergences for the TAU-bench fixture,
    THEN the bulleted list contains exactly three entries (matching the three
    divergences in scouting/candidates/tau-bench/cost-reconciliation.json), and
    each entry's agent_id, reported cost, and reconstructed cost match the
    fixture values.
    """
    import json

    text = _render_taubench_report(repo_root)
    cost_recon = json.loads(
        (repo_root / "scouting" / "candidates" / "tau-bench" / "cost-reconciliation.json")
        .read_text()
    )
    expected_divergences = cost_recon["divergences"]

    assert len(expected_divergences) == 3

    block_start = text.index("**Divergences (per run):**")
    block_end = text.index("**Caveats:**")
    block = text[block_start:block_end]

    bullet_count = block.count("\n- ")
    assert bullet_count == 3

    for d in expected_divergences:
        agent_id = d["agent_id"]
        reported = float(d["reported_cost_usd"])
        recon = float(d["reconstructed_cost_usd"])
        assert agent_id in block
        assert f"${reported:.2f}" in block
        assert f"${recon:.2f}" in block


def test_residual_risks__missing_decision_doc_renders_placeholder(
    repo_root: Path, tmp_path: Path
) -> None:
    """WHEN the renderer is run against a study whose `benchmark` resolves to a
    `scouting/<benchmark>-decision.md` path that does not exist on disk,
    THEN the Residual risks section is still emitted as the sixth `##` heading,
    AND the section's body is exactly the single placeholder line with the
    resolved benchmark slug substituted.
    """
    import shutil

    from eval_audit.ingest.hal_gaia import HalGaiaAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    # Build a shadow repo with the same scouting fixture but no decision doc.
    shadow_root = tmp_path / "shadow"
    (shadow_root / "scouting" / "candidates").mkdir(parents=True)
    shutil.copytree(
        repo_root / "scouting" / "candidates" / "gaia",
        shadow_root / "scouting" / "candidates" / "gaia",
    )
    # Intentionally do NOT copy scouting/exhibit-a-decision.md.

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")
    runs = HalGaiaAdapter().load(shadow_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=200, bootstrap_seed=42)
    text = render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=shadow_root,
        bootstrap_iterations=200,
        bootstrap_seed=42,
    )

    # Section count: exactly eight `##` headings in the listed order.
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    section_titles = [h.removeprefix("## ").strip() for h in headings]
    assert section_titles == [
        "Audit Summary",
        "Study",
        "Provenance",
        "Per-agent summary",
        "Claims",
        "Cost-quality view",
        "Residual risks",
        "Reproducibility footer",
    ]

    # Placeholder line is present with the resolved (aliased) filename.
    assert (
        "_(no scouting decision document at scouting/exhibit-a-decision.md; "
        "residual risks not surfaced.)_"
    ) in text
