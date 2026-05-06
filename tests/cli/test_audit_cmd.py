"""Acceptance tests for the practical `eval-audit audit` workflow."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_audit__ready_byo_writes_deterministic_artifacts(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    args = [
        "audit",
        str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        "--runs",
        str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
        "--out-dir",
        str(out_dir),
        "--repo-root",
        str(repo_root),
        "--bootstrap-iterations",
        "200",
    ]

    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    target_dir = out_dir / "byo-minimal"
    artifacts = {
        name: (target_dir / name).read_bytes()
        for name in ("check.json", "analysis.json", "report.md")
    }

    second = runner.invoke(app, args)
    assert second.exit_code == 0, second.output
    assert artifacts == {
        name: (target_dir / name).read_bytes()
        for name in ("check.json", "analysis.json", "report.md")
    }
    assert "study=byo-minimal" in first.output
    assert "readiness=ready_with_warnings" in first.output
    assert str(target_dir / "report.md") in first.output
    assert "claim alice_vs_bob: switch" in first.output


def test_audit__not_ready_stops_before_analysis_and_report(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    frame = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    bad = frame.with_columns(
        pl.when(pl.col("agent_id") == "alice")
        .then(pl.lit("alice-renamed"))
        .otherwise(pl.col("agent_id"))
        .alias("agent_id")
    )
    bad_path = tmp_path / "missing-agent.parquet"
    bad.write_parquet(bad_path)

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "audit",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code != 0
    assert "claim_agents_present" in result.output
    assert "Add run rows" in result.output
    assert not (out_dir / "byo-minimal" / "analysis.json").exists()
    assert not (out_dir / "byo-minimal" / "report.md").exists()


def test_audit__cross_harness_refusal_does_not_write_report(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    frame = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    bad = frame.with_columns(
        pl.when(pl.col("agent_id") == "bob")
        .then(pl.lit("other-harness"))
        .otherwise(pl.col("harness"))
        .alias("harness")
    )
    bad_path = tmp_path / "cross-harness.parquet"
    bad.write_parquet(bad_path)

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "audit",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code != 0
    assert "Cross-harness comparisons are not audit-ready" in result.output
    assert not (out_dir / "byo-minimal" / "report.md").exists()


def test_audit__html_flag_writes_optional_html(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "audit",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "200",
            "--html",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "byo-minimal" / "report.md").exists()
    html_path = out_dir / "byo-minimal" / "report.html"
    assert html_path.exists()
    assert str(html_path) in result.output
    assert "report.md</code> is the canonical reproducibility artifact" in html_path.read_text()


def test_audit__without_html_does_not_write_html(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "audit",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not (out_dir / "byo-minimal" / "report.html").exists()
