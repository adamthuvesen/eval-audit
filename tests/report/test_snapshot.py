"""Snapshot test for the Exhibit A markdown report.

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
SNAPSHOT_PATH_A = SNAPSHOTS_DIR / "exhibit-a-report.md"
SNAPSHOT_PATH_B = SNAPSHOTS_DIR / "exhibit-b-report.md"
FIXED_CLOCK = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
FIXED_GIT_COMMIT = "snapshot"
FIXED_FIXTURE_SHA = "0" * 64


def _render_exhibit_a(repo_root: Path) -> str:
    from rigor.ingest.hal_gaia import HalGaiaAdapter
    from rigor.report.markdown import render_report
    from rigor.schema import StudySpec
    from rigor.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")
    adapter = HalGaiaAdapter()
    runs = adapter.load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=2_000,
        bootstrap_seed=42,
    )


def _render_exhibit_b(repo_root: Path) -> str:
    from rigor.ingest.hal_tau_bench import HalTauBenchAdapter
    from rigor.report.markdown import render_report
    from rigor.schema import StudySpec
    from rigor.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-b.yaml")
    adapter = HalTauBenchAdapter()
    runs = adapter.load(repo_root / "scouting" / "candidates" / "tau-bench")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    return render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit=FIXED_GIT_COMMIT,
        fixture_sha256=FIXED_FIXTURE_SHA,
        repo_root=repo_root,
        bootstrap_iterations=2_000,
        bootstrap_seed=42,
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


def test_report_snapshot__exhibit_a_matches_committed_snapshot(repo_root: Path) -> None:
    rendered = _render_exhibit_a(repo_root)
    _check_snapshot(SNAPSHOT_PATH_A, rendered, "Exhibit A")


def test_report_snapshot__exhibit_b_matches_committed_snapshot(repo_root: Path) -> None:
    rendered = _render_exhibit_b(repo_root)
    _check_snapshot(SNAPSHOT_PATH_B, rendered, "Exhibit B")
