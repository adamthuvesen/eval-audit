"""Tests for CLI help framing."""

from __future__ import annotations

from typer.testing import CliRunner


def test_help__lists_portfolio_as_evidence_index() -> None:
    from eval_audit.cli import app

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "portfolio" in result.output
    assert "evidence index" in result.output
    assert "leaderboard" not in result.output.lower()


def test_audit_help__frames_one_command_artifact_generation() -> None:
    from eval_audit.cli import app

    result = CliRunner().invoke(app, ["audit", "--help"])

    assert result.exit_code == 0, result.output
    assert "check.json" in result.output
    assert "analysis.json" in result.output
    assert "report.md" in result.output
    assert "summary.json" in result.output
