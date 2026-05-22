"""Tests for the standalone `eval-audit validate` pre-flight command."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_validate__byo_example_succeeds_with_ok_message(
    runner: CliRunner, repo_root: Path
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(
        app,
        [
            "validate",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.output == "OK: 20 rows, study 'byo-minimal'\n"


def test_validate__missing_runs_path_exits_nonzero(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    missing = tmp_path / "nonexistent.parquet"
    result = runner.invoke(
        app,
        [
            "validate",
            str(missing),
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        ],
    )
    assert result.exit_code != 0
    assert "nonexistent.parquet" in result.output


def test_validate__non_parquet_runs_file_exits_nonzero_without_traceback(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    bad_runs = tmp_path / "runs.txt"
    bad_runs.write_text("not parquet")

    result = runner.invoke(
        app,
        [
            "validate",
            str(bad_runs),
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        ],
    )

    assert result.exit_code != 0
    assert "could not read runs parquet" in result.output
    assert "Traceback" not in result.output


def test_validate__malformed_parquet_names_row_and_field(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    src = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    rows = src.to_dicts()
    rows[5]["cost_provenance"] = "wrong"
    bad = pl.DataFrame(rows, strict=False)
    bad_path = tmp_path / "malformed.parquet"
    bad.write_parquet(bad_path)

    result = runner.invoke(
        app,
        [
            "validate",
            str(bad_path),
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        ],
    )
    assert result.exit_code != 0
    assert "row 5" in result.output
    assert "cost_provenance" in result.output


def test_validate__bad_study_yaml_exits_nonzero(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    """A study YAML declaring lower_is_better fails StudySpec validation."""
    from eval_audit.cli import app

    src_yaml = (repo_root / "examples" / "byo-minimal" / "study.yaml").read_text()
    bad_yaml = src_yaml.replace("higher_is_better", "lower_is_better")
    bad_path = tmp_path / "bad-study.yaml"
    bad_path.write_text(bad_yaml)

    result = runner.invoke(
        app,
        [
            "validate",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            str(bad_path),
        ],
    )
    assert result.exit_code != 0


def test_validate__rejects_non_task_primary_outcome_unit(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    src_yaml = (repo_root / "examples" / "byo-minimal" / "study.yaml").read_text()
    bad_path = tmp_path / "bad-unit.yaml"
    bad_path.write_text(src_yaml.replace("unit: task", "unit: request"))

    result = runner.invoke(
        app,
        [
            "validate",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            str(bad_path),
        ],
    )

    assert result.exit_code != 0
    assert "unit" in result.output
    assert "task" in result.output


def test_validate__rejects_target_mde_above_one(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    src_yaml = (repo_root / "examples" / "byo-minimal" / "study.yaml").read_text()
    bad_path = tmp_path / "bad-mde.yaml"
    bad_path.write_text(src_yaml.replace("target_mde: 0.05", "target_mde: 1.50"))

    result = runner.invoke(
        app,
        [
            "validate",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            str(bad_path),
        ],
    )

    assert result.exit_code != 0
    assert "target_mde" in result.output
    assert "<= 1" in result.output


def test_validate__missing_study_path_exits_nonzero(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    missing = tmp_path / "nonexistent.yaml"
    result = runner.invoke(
        app,
        [
            "validate",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            str(missing),
        ],
    )
    assert result.exit_code != 0
    assert "nonexistent.yaml" in result.output


def test_validate__has_no_side_effects(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    """validate must not write files or create directories anywhere."""
    from eval_audit.cli import app

    before = sorted(p.name for p in tmp_path.iterdir())
    result = runner.invoke(
        app,
        [
            "validate",
            str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
        ],
    )
    after = sorted(p.name for p in tmp_path.iterdir())
    assert result.exit_code == 0
    assert before == after, "validate created files in tmp_path"
