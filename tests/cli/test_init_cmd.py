"""Tests for the `eval-audit init` scaffolding command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_init__creates_four_expected_files(runner: CliRunner, tmp_path: Path) -> None:
    from eval_audit.cli import app

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output

    target = tmp_path / "my-study"
    assert sorted(p.name for p in target.iterdir()) == [
        "README.md",
        "make_runs.py",
        "runs.parquet",
        "study.yaml",
    ]


def test_init__readme_names_current_run_commands(runner: CliRunner, tmp_path: Path) -> None:
    from eval_audit.cli import app

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output

    readme = (tmp_path / "my-study" / "README.md").read_text()
    assert "eval-audit audit study.yaml --runs runs.parquet" in readme
    assert "eval-audit report ..." not in readme


def test_init__scaffolded_study_yaml_parses_with_correct_id(
    runner: CliRunner, tmp_path: Path
) -> None:
    from eval_audit.cli import app
    from eval_audit.schema import StudySpec

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output

    study = StudySpec.from_yaml(tmp_path / "my-study" / "study.yaml")
    assert study.id == "my-study"
    assert study.benchmark == "my-study"
    assert study.harness == "my-study"


def test_init__scaffolded_parquet_validates(runner: CliRunner, tmp_path: Path) -> None:
    from eval_audit.cli import app
    from eval_audit.ingest import load_run_records

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output

    frame = load_run_records(tmp_path / "my-study" / "runs.parquet")
    assert frame.height == 20


def test_init__round_trips_through_validate(runner: CliRunner, tmp_path: Path) -> None:
    from eval_audit.cli import app

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output

    validate = runner.invoke(
        app,
        [
            "validate",
            str(tmp_path / "my-study" / "runs.parquet"),
            str(tmp_path / "my-study" / "study.yaml"),
        ],
    )
    assert validate.exit_code == 0, validate.output
    assert "OK" in validate.output


def test_init__round_trips_through_analyze(
    runner: CliRunner, tmp_path: Path, repo_root: Path
) -> None:
    from eval_audit.cli import app

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output

    out_dir = tmp_path / "reports"
    analyze = runner.invoke(
        app,
        [
            "analyze",
            str(tmp_path / "my-study" / "study.yaml"),
            "--runs",
            str(tmp_path / "my-study" / "runs.parquet"),
            "--out-dir",
            str(out_dir),
            "--repo-root",
            str(repo_root),
            "--bootstrap-iterations",
            "200",
        ],
    )
    assert analyze.exit_code == 0, analyze.output
    assert (out_dir / "my-study" / "analysis.json").exists()


@pytest.mark.parametrize(
    "bad_slug",
    [
        "My_Study",  # uppercase + underscore
        "study/foo",  # slash (typer + slug validator both reject)
        "study with space",  # whitespace
        "",  # empty
    ],
)
def test_init__rejects_bad_slugs(runner: CliRunner, tmp_path: Path, bad_slug: str) -> None:
    from eval_audit.cli import app

    result = runner.invoke(app, ["init", bad_slug, "--cwd", str(tmp_path)])
    assert result.exit_code != 0
    # The slug validator's message names the constraint; some inputs may be
    # rejected earlier by typer's option parsing instead. Either way is fine.
    if bad_slug:
        assert not (tmp_path / bad_slug).exists()


def test_init__leading_hyphen_slug_is_rejected(runner: CliRunner, tmp_path: Path) -> None:
    """Leading-hyphen names are unsafe because they look like CLI flags. Use `--` to separate."""
    from eval_audit.cli import app

    # With `--` separator, the leading hyphen reaches our handler, which rejects it.
    result = runner.invoke(app, ["init", "--cwd", str(tmp_path), "--", "-bad-slug"])
    assert result.exit_code != 0
    assert "slug" in result.output or "match" in result.output


def test_init__digit_prefix_is_allowed(runner: CliRunner, tmp_path: Path) -> None:
    from eval_audit.cli import app

    result = runner.invoke(app, ["init", "1study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "1study" / "study.yaml").exists()


def test_init__refuses_to_clobber_non_empty_directory(runner: CliRunner, tmp_path: Path) -> None:
    from eval_audit.cli import app

    target = tmp_path / "my-study"
    target.mkdir()
    (target / "important.txt").write_text("do not overwrite me")

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code != 0
    assert "my-study" in result.output
    assert (target / "important.txt").read_text() == "do not overwrite me"
    assert not (target / "study.yaml").exists()


def test_init__accepts_existing_empty_directory(runner: CliRunner, tmp_path: Path) -> None:
    from eval_audit.cli import app

    target = tmp_path / "my-study"
    target.mkdir()  # empty

    result = runner.invoke(app, ["init", "my-study", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (target / "study.yaml").exists()
