"""Snapshot test for the GAIA HAL Generalist markdown report.

Re-renders the report from the committed fixture under a fixed clock and
fixed git/sha placeholders, then diffs against the committed snapshot. A
diff fails the test, which forces an explicit snapshot update on PR.

Update with:
    UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

SNAPSHOTS_DIR = Path(__file__).parent.parent / "report_snapshots"
SNAPSHOT_PATH_A = SNAPSHOTS_DIR / "gaia-hal-generalist-report.md"
SNAPSHOT_PATH_B = SNAPSHOTS_DIR / "tau-bench-airline-tool-calling-report.md"
SNAPSHOT_PATH_C = SNAPSHOTS_DIR / "humaneval-direct-completion-report.md"
SNAPSHOT_PATH_GALLERY = SNAPSHOTS_DIR / "decision-gallery-report.md"
SNAPSHOT_PATH_SWE_BENCH = SNAPSHOTS_DIR / "swe-bench-verified-openhands-report.md"
SNAPSHOT_PATH_TERMINAL_BENCH = SNAPSHOTS_DIR / "terminal-bench-2-mux-report.md"
FIXED_CLOCK = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
FIXED_GIT_COMMIT = "snapshot"
FIXED_FIXTURE_SHA = "0" * 64


def _render_gaia_hal_generalist(repo_root: Path, readiness_kwargs) -> str:
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "gaia-hal-generalist.yaml")
    adapter = HalGaiaAdapter()
    runs = adapter.load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=10_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=10_000,
        bootstrap_seed=42,
        **readiness_kwargs(study, runs, repo_root),
    )


def _render_tau_bench_airline_tool_calling(repo_root: Path, readiness_kwargs) -> str:
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "tau-bench-airline-tool-calling.yaml")
    adapter = HalTauBenchAdapter()
    runs = adapter.load(repo_root / "scouting" / "candidates" / "tau-bench")
    result = analyze(study, runs, bootstrap_iterations=10_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=10_000,
        bootstrap_seed=42,
        **readiness_kwargs(study, runs, repo_root),
    )


def _check_snapshot(snapshot_path: Path, rendered: str, label: str) -> None:
    if os.getenv("UPDATE_SNAPSHOTS") == "1":
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(rendered)
        pytest.skip(f"snapshot updated at {snapshot_path}")

    if not snapshot_path.exists():
        pytest.fail(
            f"snapshot file missing at {snapshot_path}; "
            "run UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py to create it"
        )

    expected = snapshot_path.read_text()
    assert rendered == expected, (
        f"rendered {label} report does not match committed snapshot. "
        "If the change is intentional, regenerate with "
        "UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py "
        "and review the diff in the PR."
    )


def _render_humaneval_direct_completion(repo_root: Path, readiness_kwargs) -> str:
    """Render HumanEval Direct Completion — controlled original-evidence audit on HumanEval.

    Uses the generic BYO loader against the committed canonical parquet at
    ``examples/humaneval-direct-completion/runs.parquet``. HumanEval Direct Completion is original evidence
    (analysis_mode=preregistered), so the parquet is the source of truth —
    not regenerated from a ``make_runs.py`` script at session start.
    """
    from eval_audit.ingest.generic import load_run_records
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "humaneval-direct-completion.yaml")
    runs = load_run_records(repo_root / "examples" / "humaneval-direct-completion" / "runs.parquet")
    result = analyze(study, runs, bootstrap_iterations=10_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=10_000,
        bootstrap_seed=42,
        **readiness_kwargs(study, runs, repo_root),
    )


def _render_decision_gallery(repo_root: Path, readiness_kwargs) -> str:
    from eval_audit.ingest.generic import load_run_records
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "decision-gallery.yaml")
    runs = load_run_records(repo_root / "examples" / "decision-gallery" / "runs.parquet")
    result = analyze(study, runs, bootstrap_iterations=10_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=10_000,
        bootstrap_seed=42,
        **readiness_kwargs(study, runs, repo_root),
    )


def _render_swe_bench_verified_openhands(repo_root: Path, readiness_kwargs) -> str:
    """Render the SWE-bench Verified OpenHands public-submission audit.

    The fixture under ``examples/swe-bench-verified-openhands/runs.parquet`` is
    regenerated by ``tools/regenerate_swe_bench_verified.py`` from public
    artifacts (see ``provenance.json`` for source URLs and SHA-256 hashes).
    Cost provenance is `cost_not_available`; the rendered report suppresses
    every cost-derived view.
    """
    from eval_audit.ingest.swe_bench_verified import SweBenchVerifiedAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "swe-bench-verified-openhands.yaml")
    adapter = SweBenchVerifiedAdapter()
    runs = adapter.load(repo_root / "examples" / "swe-bench-verified-openhands")
    result = analyze(study, runs, bootstrap_iterations=10_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=10_000,
        bootstrap_seed=42,
        **readiness_kwargs(study, runs, repo_root),
    )


def _render_terminal_bench_2_mux(repo_root: Path, readiness_kwargs) -> str:
    """Render the Terminal-Bench 2.0 Mux public-submission audit."""
    from eval_audit.ingest.terminal_bench import TerminalBenchMuxAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "terminal-bench-2-mux.yaml")
    adapter = TerminalBenchMuxAdapter()
    runs = adapter.load(repo_root / "examples" / "terminal-bench-2-mux")
    result = analyze(study, runs, bootstrap_iterations=10_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=10_000,
        bootstrap_seed=42,
        **readiness_kwargs(study, runs, repo_root),
    )


def test_report_snapshot__gaia_hal_generalist_matches_committed_snapshot(
    repo_root: Path, readiness_kwargs
) -> None:
    rendered = _render_gaia_hal_generalist(repo_root, readiness_kwargs)
    _check_snapshot(SNAPSHOT_PATH_A, rendered, "GAIA HAL Generalist")


def test_report_snapshot__tau_bench_airline_tool_calling_matches_committed_snapshot(
    repo_root: Path, readiness_kwargs
) -> None:
    rendered = _render_tau_bench_airline_tool_calling(repo_root, readiness_kwargs)
    _check_snapshot(SNAPSHOT_PATH_B, rendered, "TAU-bench Airline Tool Calling")


def test_report_snapshot__humaneval_direct_completion_matches_committed_snapshot(
    repo_root: Path, readiness_kwargs
) -> None:
    rendered = _render_humaneval_direct_completion(repo_root, readiness_kwargs)
    _check_snapshot(SNAPSHOT_PATH_C, rendered, "HumanEval Direct Completion")


def test_humaneval_direct_completion_runs_parquet__cost_provenance_is_partial(
    repo_root: Path,
) -> None:
    """The committed HumanEval Direct Completion parquet must use cost_provenance='partial'.

    The Anthropic Messages API does not expose an independent provider-side
    run total, so reconciliation is impossible by construction. 'partial'
    is the honest provenance label — see scouting/humaneval-direct-completion/normalize.py
    module docstring.
    """
    import polars as pl

    runs = pl.read_parquet(repo_root / "examples" / "humaneval-direct-completion" / "runs.parquet")
    provenance_values = sorted(runs["cost_provenance"].unique().to_list())
    assert provenance_values == ["partial"], (
        f"HumanEval Direct Completion parquet must use cost_provenance='partial' (got {provenance_values})"
    )


def test_report_snapshot__decision_gallery_matches_committed_snapshot(
    repo_root: Path, readiness_kwargs
) -> None:
    rendered = _render_decision_gallery(repo_root, readiness_kwargs)
    _check_snapshot(SNAPSHOT_PATH_GALLERY, rendered, "Decision pattern gallery")


def test_report_snapshot__swe_bench_verified_openhands_matches_committed_snapshot(
    repo_root: Path, readiness_kwargs
) -> None:
    rendered = _render_swe_bench_verified_openhands(repo_root, readiness_kwargs)
    _check_snapshot(SNAPSHOT_PATH_SWE_BENCH, rendered, "SWE-bench Verified OpenHands")


def test_report_snapshot__terminal_bench_2_mux_matches_committed_snapshot(
    repo_root: Path, readiness_kwargs
) -> None:
    rendered = _render_terminal_bench_2_mux(repo_root, readiness_kwargs)
    _check_snapshot(SNAPSHOT_PATH_TERMINAL_BENCH, rendered, "Terminal-Bench 2.0 Mux")
