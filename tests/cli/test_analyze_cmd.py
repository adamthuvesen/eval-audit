"""Acceptance tests for the `eval-audit analyze` CLI command."""

from __future__ import annotations

from pathlib import Path

import click
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
            str(repo_root / "studies" / "gaia-hal-generalist.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--bootstrap-iterations", "0",
        ],
    )

    assert result.exit_code != 0
    plain_output = click.unstyle(result.output)
    assert "Invalid value" in plain_output
    assert "bootstrap" in plain_output
    assert "iterations" in plain_output
    assert not (out_dir / "gaia-hal-generalist" / "analysis.json").exists()


def test_cli_analyze__invalid_study_yaml_exits_nonzero_without_traceback(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    bad_study = tmp_path / "bad-study.yaml"
    bad_study.write_text("schema_version: 1\nid: bad\n")
    out_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "analyze",
            str(bad_study),
            "--out-dir",
            str(out_dir),
            "--bootstrap-iterations",
            "10",
        ],
    )

    assert result.exit_code == 2
    assert "invalid study YAML" in result.output
    assert "Field required" in result.output
    assert "Traceback" not in result.output
    assert not out_dir.exists()


def test_cli_analyze__zero_success_cost_per_success_serializes_as_null(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    import json

    import polars as pl

    from eval_audit.cli import app

    source = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    zero_success_runs = source.with_columns(
        success=pl.lit(False),
        partial_credit=pl.lit(False),
    )
    runs_path = tmp_path / "zero-success-runs.parquet"
    zero_success_runs.write_parquet(runs_path)
    out_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(runs_path),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code == 0, result.output
    analysis_text = (out_dir / "byo-minimal" / "analysis.json").read_text()
    assert "Infinity" not in analysis_text
    assert "NaN" not in analysis_text

    analysis = json.loads(analysis_text)
    assert {agent["cost_per_success_usd"] for agent in analysis["per_agent"]} == {None}


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


def test_cli_analyze__terminal_bench_resolves_examples_backed_fixture(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Terminal-Bench 2.0 public submissions resolve through examples/<study.id>."""
    import json

    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "studies" / "terminal-bench-2-mux.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--bootstrap-iterations", "200",
        ],
    )

    assert result.exit_code == 0, result.output
    analysis_path = out_dir / "terminal-bench-2-mux" / "analysis.json"
    assert analysis_path.exists()

    analysis = json.loads(analysis_path.read_text())
    assert analysis["pareto_status"] == "suppressed_cost_not_available"
    by_id = {a["agent_id"]: a for a in analysis["per_agent"]}
    assert by_id["Mux__GPT-5.3-Codex"]["total_cost_usd"] is None
    assert by_id["Mux__Claude-Opus-4.6"]["total_cost_usd"] is None
