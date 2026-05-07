"""Acceptance tests for the audit portfolio evidence-index command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner


def _run_byo_audit(
    *,
    runner: CliRunner,
    repo_root: Path,
    out_dir: Path,
) -> None:
    from eval_audit.cli import app

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


def test_portfolio__renders_markdown_index_from_summary_json(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    runner = CliRunner()
    reports_dir = tmp_path / "reports"
    _run_byo_audit(runner=runner, repo_root=repo_root, out_dir=reports_dir)
    out = tmp_path / "portfolio.md"

    result = runner.invoke(app, ["portfolio", str(reports_dir), "--out", str(out)])

    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert "Evidence index for declared audits" in text
    assert "leaderboard" not in text.lower()
    assert "best model" not in text.lower()
    assert "global rank" not in text.lower()
    assert "| byo-minimal | alice_vs_bob | alice | bob | switch | ready_with_warnings |" in text


def test_portfolio__json_output_is_stable_and_machine_checkable(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    runner = CliRunner()
    reports_dir = tmp_path / "reports"
    _run_byo_audit(runner=runner, repo_root=repo_root, out_dir=reports_dir)
    args = ["portfolio", str(reports_dir), "--json"]

    first = runner.invoke(app, args)
    second = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert first.output == second.output
    payload = json.loads(first.output)
    row = payload["rows"][0]
    assert {
        "study_id",
        "claim_id",
        "verdict",
        "readiness",
        "delta",
        "ci_low",
        "ci_high",
        "cost_provenance",
        "artifact_status",
    }.issubset(row)
    assert row["artifact_status"] == "complete"


def test_portfolio__reports_missing_and_stale_summaries_without_aborting(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    runner = CliRunner()
    reports_dir = tmp_path / "reports"
    _run_byo_audit(runner=runner, repo_root=repo_root, out_dir=reports_dir)

    missing = reports_dir / "missing-summary"
    missing.mkdir()
    (missing / "report.md").write_text("placeholder")

    stale = reports_dir / "stale-summary"
    stale.mkdir()
    source = reports_dir / "byo-minimal"
    for name in ("check.json", "analysis.json", "report.md", "summary.json"):
        (stale / name).write_bytes((source / name).read_bytes())
    (stale / "report.md").write_text("changed after summary generation")

    result = runner.invoke(app, ["portfolio", str(reports_dir), "--json"])

    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["rows"]
    statuses = {row["study_id"]: row["artifact_status"] for row in rows}
    assert statuses["byo-minimal"] == "complete"
    assert statuses["missing-summary"] == "missing_summary"
    assert statuses["stale-summary"] == "stale_summary"
