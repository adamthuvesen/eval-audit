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


def test_cli_analyze__swe_bench_verified_resolves_examples_backed_fixture(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """WHEN analyze is invoked on the SWE-bench Verified study WITHOUT --runs,
    THEN the CLI resolves the examples-backed adapter and writes analysis.json
    with cost-suppressed agent summaries.

    Regression guard: the CLI used to fail with `no ingest adapter for
    benchmark='swe-bench-verified'` because the adapter was never registered
    against the benchmark name.
    """
    import json

    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "studies" / "swe-bench-verified-openhands.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--bootstrap-iterations", "200",
        ],
    )

    assert result.exit_code == 0, result.output
    analysis_path = out_dir / "swe-bench-verified-openhands" / "analysis.json"
    assert analysis_path.exists()

    analysis = json.loads(analysis_path.read_text())
    assert analysis["pareto_status"] == "suppressed_cost_not_available"
    by_id = {a["agent_id"]: a for a in analysis["per_agent"]}
    assert by_id["20251127_openhands_claude-opus-4-5"]["total_cost_usd"] is None
    assert by_id["20250807_openhands_gpt5"]["total_cost_usd"] is None
