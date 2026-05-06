"""Tests for the `eval-audit check` audit-readiness command."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_check__byo_example_succeeds_with_warning_status(
    runner: CliRunner, repo_root: Path
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--repo-root",
            str(repo_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "status: ready_with_warnings" in result.output
    assert "residual_risks_source" in result.output


def test_check__json_output_is_stable_and_has_no_timestamps(
    runner: CliRunner, repo_root: Path
) -> None:
    from eval_audit.cli import app

    args = [
        "check",
        str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        "--runs",
        str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
        "--repo-root",
        str(repo_root),
        "--json",
    ]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert first.output == second.output

    payload = json.loads(first.output)
    assert set(payload) == {"checks", "status", "study_id"}
    assert payload["study_id"] == "byo-minimal"
    assert "timestamp" not in first.output.lower()
    assert [check["id"] for check in payload["checks"]] == [
        "study_loads",
        "runs_load",
        "claim_agents_present",
        "claimed_rows_match_study_harness",
        "paired_tasks_complete",
        "outcome_supported",
        "cost_provenance_explicit",
        "target_mde_declared",
        "residual_risks_source",
    ]
    for check in payload["checks"]:
        assert set(check) == {
            "details",
            "fix_suggestion",
            "id",
            "message",
            "severity",
            "status",
        }
        if check["status"] == "pass":
            assert check["fix_suggestion"] is None
        else:
            assert check["fix_suggestion"]


def test_check__out_writes_json_while_preserving_human_stdout(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    out = tmp_path / "check.json"
    result = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--repo-root",
            str(repo_root),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "status: ready_with_warnings" in result.output
    payload = json.loads(out.read_text())
    assert payload["study_id"] == "byo-minimal"


def test_check__fails_when_claimed_agent_is_absent(
    runner: CliRunner, repo_root: Path, tmp_path: Path
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

    result = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "not_ready"
    check = _check_by_id(payload, "claim_agents_present")
    assert check["severity"] == "error"
    assert check["status"] == "fail"
    assert check["fix_suggestion"]
    assert "alice" in str(check["details"])


def test_check__fails_when_tasks_are_not_paired(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    frame = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    bad = frame.filter(~((pl.col("agent_id") == "bob") & (pl.col("task_id") == "task_01")))
    bad_path = tmp_path / "unpaired.parquet"
    bad.write_parquet(bad_path)

    result = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    check = _check_by_id(payload, "paired_tasks_complete")
    assert payload["status"] == "not_ready"
    assert check["severity"] == "error"
    assert check["status"] == "fail"
    assert "paired task rows" in check["fix_suggestion"]
    assert check["details"]["missing_control_task_counts"] == [1]


def test_check__fails_for_cross_harness_claimed_rows(
    runner: CliRunner, repo_root: Path, tmp_path: Path
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

    result = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    check = _check_by_id(payload, "claimed_rows_match_study_harness")
    assert payload["status"] == "not_ready"
    assert check["severity"] == "error"
    assert check["status"] == "fail"
    assert "single-harness paired comparison" in check["fix_suggestion"]
    assert "other-harness" in str(check["details"])


def test_check__missing_target_mde_is_warning(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    study_text = (repo_root / "examples" / "byo-minimal" / "study.yaml").read_text()
    study_path = tmp_path / "study-no-mde.yaml"
    study_path.write_text(study_text.replace("target_mde: 0.05", "target_mde: null"))

    result = runner.invoke(
        app,
        [
            "check",
            str(study_path),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    check = _check_by_id(payload, "target_mde_declared")
    assert payload["status"] == "ready_with_warnings"
    assert check["severity"] == "warning"
    assert check["status"] == "fail"
    assert "inference.target_mde" in check["fix_suggestion"]


def test_check__as_reported_only_cost_provenance_is_warning(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    frame = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    as_reported = frame.with_columns(
        reconstructed_per_task_cost_usd=pl.lit(None, dtype=pl.Float64),
        cost_provenance=pl.lit("as_reported_only"),
    )
    runs_path = tmp_path / "as-reported.parquet"
    as_reported.write_parquet(runs_path)

    result = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(runs_path),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    check = _check_by_id(payload, "cost_provenance_explicit")
    assert payload["status"] == "ready_with_warnings"
    assert check["severity"] == "warning"
    assert check["status"] == "fail"
    assert "as_reported_only" in check["message"]
    assert "as_reported_only" in check["fix_suggestion"]


def test_check__cost_not_available_cost_provenance_is_warning(
    runner: CliRunner, repo_root: Path
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(
        app,
        [
            "check",
            str(repo_root / "studies" / "swe-bench-verified-openhands.yaml"),
            "--runs",
            str(repo_root / "examples" / "swe-bench-verified-openhands" / "runs.parquet"),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    check = _check_by_id(payload, "cost_provenance_explicit")
    assert payload["status"] == "ready_with_warnings"
    assert check["severity"] == "warning"
    assert check["status"] == "fail"
    assert "cost_not_available" in check["message"]
    assert "cost_not_available" in check["fix_suggestion"]


def _check_by_id(payload: dict, check_id: str) -> dict:
    by_id = {check["id"]: check for check in payload["checks"]}
    return by_id[check_id]
