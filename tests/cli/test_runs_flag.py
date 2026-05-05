"""Tests for the --runs PATH flag on `eval-audit analyze` and `eval-audit report`."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_runs_flag__analyze_with_byo_parquet_writes_analysis_json(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs", str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--bootstrap-iterations", "500",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "byo-minimal" / "analysis.json").exists()


def test_runs_flag__report_with_byo_parquet_writes_nine_section_report(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "report",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs", str(repo_root / "examples" / "byo-minimal" / "runs.parquet"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--skip-validation",
            "--bootstrap-iterations", "500",
        ],
    )

    assert result.exit_code == 0, result.output
    target = out_dir / "byo-minimal" / "report.md"
    assert target.exists()

    text = target.read_text()
    expected = [
        "## Audit Summary",
        "## Study",
        "## Provenance",
        "## Per-agent summary",
        "## Claims",
        "## Robustness Review",
        "## Cost-quality view",
        "## Residual risks",
        "## Reproducibility footer",
    ]
    last = -1
    for section in expected:
        pos = text.find(section)
        assert pos != -1, f"missing section: {section}"
        assert pos > last, f"section out of order: {section}"
        last = pos


def test_runs_flag__no_flag_preserves_adapter_path_for_existing_exhibits(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    """Backward compat regression guard: existing studies still work without --runs."""
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "studies" / "exhibit-a.yaml"),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
            "--bootstrap-iterations", "200",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "exhibit-a" / "analysis.json").exists()


def test_runs_flag__missing_path_exits_nonzero_with_clear_error(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    from eval_audit.cli import app

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs", "nonexistent.parquet",
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
        ],
    )

    assert result.exit_code != 0
    assert "nonexistent.parquet" in result.output
    assert not (out_dir / "byo-minimal" / "analysis.json").exists()


def test_runs_flag__malformed_parquet_names_row_and_field(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    """A parquet with a bad enum value at row 5 surfaces row index and field in stderr."""
    from eval_audit.cli import app

    src = pl.read_parquet(repo_root / "examples" / "byo-minimal" / "runs.parquet")
    rows = src.to_dicts()
    rows[5]["cost_provenance"] = "wrong"
    bad = pl.DataFrame(rows, strict=False)
    bad_path = tmp_path / "malformed.parquet"
    bad.write_parquet(bad_path)

    out_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "analyze",
            str(repo_root / "examples" / "byo-minimal" / "study.yaml"),
            "--runs", str(bad_path),
            "--out-dir", str(out_dir),
            "--repo-root", str(repo_root),
        ],
    )

    assert result.exit_code != 0
    output = result.output + (str(result.exception) if result.exception else "")
    assert "row 5" in output, output
    assert "cost_provenance" in output, output
