"""Acceptance tests for the `eval-audit report` CLI command."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import click
import polars as pl
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
    """WHEN the user runs `eval-audit report studies/gaia-hal-generalist.yaml` with no flags,
    THEN the synthetic-validation suite runs first and the report is only
    written if it passes.
    """
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "report",
            str(repo_root / "studies" / "gaia-hal-generalist.yaml"),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
        ],
    )
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0, f"report cmd failed: {result.output}"
    # Validation must have run before report — its marker output appears in output.
    assert "synthetic_validation" in result.output or "synthetic-validation" in result.output
    # Report file written.
    assert (out_dir / "gaia-hal-generalist" / "report.md").exists()


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
            str(repo_root / "studies" / "gaia-hal-generalist.yaml"),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--skip-validation",
        ],
    )
    assert result.exit_code == 0
    assert "WARNING: synthetic validation skipped" in result.output
    assert (out_dir / "gaia-hal-generalist" / "report.md").exists()


def test_cli_report__invalid_study_yaml_exits_nonzero_without_traceback(
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
            "report",
            str(bad_study),
            "--out-dir",
            str(out_dir),
            "--skip-validation",
            "--bootstrap-iterations",
            "10",
        ],
    )

    assert result.exit_code == 2
    assert "invalid study YAML" in result.output
    assert "Field required" in result.output
    assert "Traceback" not in result.output
    assert "synthetic validation skipped" not in result.output
    assert not out_dir.exists()


def test_cli_report__writes_readiness_json_and_footer_hash(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "report",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--skip-validation",
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code == 0, result.output
    report_path = out_dir / "byo-minimal" / "report.md"
    check_path = out_dir / "byo-minimal" / "check.json"
    assert report_path.exists()
    assert check_path.exists()

    payload = json.loads(check_path.read_text())
    digest = hashlib.sha256(check_path.read_bytes()).hexdigest()
    report = report_path.read_text()
    assert payload["status"] in {"ready", "ready_with_warnings"}
    assert f"- **evidence_readiness:** `{payload['status']}`" in report
    assert f"- **check_sha256:** `{digest}`" in report


def test_cli_report__refuses_not_ready_evidence(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    frame = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    bad = frame.filter(~((pl.col("agent_id") == "bob") & (pl.col("task_id") == "task_01")))
    bad_path = tmp_path / "unpaired.parquet"
    bad.write_parquet(bad_path)

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "report",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--skip-validation",
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code != 0
    assert "evidence readiness check FAILED" in result.output
    assert "paired_tasks_complete" in result.output
    assert not (out_dir / "byo-minimal" / "report.md").exists()

    # The failure message must point users at a runnable `check --out` line
    # that captures the diagnostic JSON to the configured out-dir/study-id path.
    expected_check_path = out_dir / "byo-minimal" / "check.json"
    expected_invocation = (
        f"eval-audit check {repo_root / 'examples' / 'byo-minimal' / 'study.yaml'} "
        f"--runs {bad_path} --out {expected_check_path}"
    )
    assert expected_invocation in result.output

    # Running the suggested invocation should write the readiness JSON to the
    # named --out path. `check` exits non-zero on not_ready evidence, but the
    # file must still be written so users can inspect it.
    follow_up = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--repo-root",
            str(repo_root),
            "--out",
            str(expected_check_path),
        ],
    )
    assert follow_up.exit_code != 0
    assert expected_check_path.exists()


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
            str(repo_root / "studies" / "gaia-hal-generalist.yaml"),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--skip-validation",
            "--bootstrap-iterations",
            "0",
        ],
    )

    assert result.exit_code != 0
    plain_output = click.unstyle(result.output)
    assert "Invalid value" in plain_output
    assert "bootstrap" in plain_output
    assert "iterations" in plain_output
    assert not (out_dir / "gaia-hal-generalist" / "report.md").exists()
