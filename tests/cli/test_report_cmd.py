"""Acceptance tests for the `eval-audit report` CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_report__default_invocation_runs_validation_first(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """WHEN the user runs `eval-audit report studies/exhibit-a.yaml` with no flags,
    THEN the synthetic-validation suite runs first and the report is only
    written if it passes.
    """
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "report",
            str(repo_root / "studies" / "exhibit-a.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
        ],
    )
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0, f"report cmd failed: {result.output}"
    # Validation must have run before report — its marker output appears in output.
    assert "synthetic_validation" in result.output or "synthetic-validation" in result.output
    # Report file written.
    assert (out_dir / "exhibit-a" / "report.md").exists()


def test_cli_report__skip_flag_warns(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """WHEN the user passes --skip-validation,
    THEN a warning containing 'WARNING: synthetic validation skipped' is written
    to stderr before the report is written.
    """
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "report",
            str(repo_root / "studies" / "exhibit-a.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--skip-validation",
        ],
    )
    assert result.exit_code == 0
    assert "WARNING: synthetic validation skipped" in result.output
    assert (out_dir / "exhibit-a" / "report.md").exists()


def test_cli_report__rejects_zero_bootstrap_iterations(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """WHEN report is invoked with --bootstrap-iterations 0,
    THEN Typer rejects the option before writing a report.
    """
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "report",
            str(repo_root / "studies" / "exhibit-a.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--skip-validation",
            "--bootstrap-iterations", "0",
        ],
    )

    assert result.exit_code != 0
    assert "bootstrap-iterations" in result.output
    assert not (out_dir / "exhibit-a" / "report.md").exists()
