"""Acceptance tests for the `eval-audit analyze` CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_analyze__rejects_zero_bootstrap_iterations(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """WHEN analyze is invoked with --bootstrap-iterations 0,
    THEN Typer rejects the option before writing analysis output.
    """
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "studies" / "exhibit-a.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--bootstrap-iterations", "0",
        ],
    )

    assert result.exit_code != 0
    assert "bootstrap-iterations" in result.output
    assert not (out_dir / "exhibit-a" / "analysis.json").exists()
