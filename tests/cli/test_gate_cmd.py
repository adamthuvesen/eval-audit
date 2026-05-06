"""Acceptance tests for the `eval-audit gate` CI command."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_gate__passes_when_readiness_and_verdict_are_allowed(
    runner: CliRunner,
    repo_root: Path,
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(
        app,
        [
            "gate",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--repo-root",
            str(repo_root),
            "--allow-verdict",
            "switch",
            "--allow-verdict",
            "hold",
            "--min-readiness",
            "ready_with_warnings",
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "gate pass" in result.output
    assert "readiness=ready_with_warnings" in result.output
    assert "claim alice_vs_bob: switch" in result.output


def test_gate__fails_on_disallowed_verdict(
    runner: CliRunner,
    repo_root: Path,
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(
        app,
        [
            "gate",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--repo-root",
            str(repo_root),
            "--allow-verdict",
            "hold",
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code != 0
    assert "alice_vs_bob" in result.output
    assert "switch" in result.output
    assert "hold" in result.output


def test_gate__json_output_is_stable_and_machine_checkable(
    runner: CliRunner,
    repo_root: Path,
) -> None:
    from eval_audit.cli import app

    args = [
        "gate",
        str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        "--runs",
        str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
        "--repo-root",
        str(repo_root),
        "--allow-verdict",
        "switch",
        "--json",
        "--bootstrap-iterations",
        "200",
    ]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert first.output == second.output
    payload = json.loads(first.output)
    assert set(payload) == {
        "allowed_verdicts",
        "claims",
        "failures",
        "readiness",
        "status",
        "study_id",
    }
    assert payload["status"] == "pass"
    assert "timestamp" not in first.output.lower()


def test_gate__rejects_unknown_verdict_name(
    runner: CliRunner,
    repo_root: Path,
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(
        app,
        [
            "gate",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--allow-verdict",
            "better",
        ],
    )

    assert result.exit_code != 0
    assert "better" in result.output
    assert "switch" in result.output
    assert "inconclusive_no_action" in result.output


def test_gate__fails_when_not_ready_with_fix_suggestion(
    runner: CliRunner,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    from eval_audit.cli import app

    frame = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    bad = frame.filter(~((pl.col("agent_id") == "bob") & (pl.col("task_id") == "task_01")))
    bad_path = tmp_path / "unpaired.parquet"
    bad.write_parquet(bad_path)

    result = runner.invoke(
        app,
        [
            "gate",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--repo-root",
            str(repo_root),
            "--allow-verdict",
            "switch",
            "--json",
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "fail"
    assert payload["readiness"] == "not_ready"
    assert payload["failures"][0]["check_id"] == "paired_tasks_complete"
    assert "paired task rows" in payload["failures"][0]["fix_suggestion"]


def test_gate__fails_when_min_readiness_is_stricter_than_evidence(
    runner: CliRunner,
    repo_root: Path,
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(
        app,
        [
            "gate",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--repo-root",
            str(repo_root),
            "--allow-verdict",
            "switch",
            "--min-readiness",
            "ready",
            "--bootstrap-iterations",
            "200",
        ],
    )

    assert result.exit_code != 0
    assert "ready_with_warnings does not meet minimum ready" in result.output


def test_gate__cross_harness_refusal_is_not_eligible(
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

    result = runner.invoke(
        app,
        [
            "gate",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs",
            str(bad_path),
            "--repo-root",
            str(repo_root),
            "--allow-verdict",
            "switch",
        ],
    )

    assert result.exit_code != 0
    assert "Cross-harness comparisons are not audit-ready" in result.output
