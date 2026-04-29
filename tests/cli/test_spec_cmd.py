"""Acceptance tests for the `rigor spec` CLI sub-app."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_spec_validate__exits_zero_on_valid_file(runner: CliRunner, repo_root: Path) -> None:
    """WHEN `rigor spec validate studies/exhibit-a.yaml` is invoked,
    THEN exit code is 0 and stdout contains a single-line success message naming the study id.
    """
    from rigor.cli import app

    result = runner.invoke(app, ["spec", "validate", str(repo_root / "studies" / "exhibit-a.yaml")])
    assert result.exit_code == 0, result.output
    assert "exhibit-a" in result.output
    assert "OK" in result.output


def test_cli_spec_validate__exits_nonzero_on_malformed_file(
    runner: CliRunner, tmp_path: Path
) -> None:
    """WHEN `rigor spec validate` is invoked against a YAML file missing required fields,
    THEN exit code is non-zero and the pydantic ValidationError is printed verbatim.
    """
    from rigor.cli import app

    bad = tmp_path / "broken.yaml"
    bad.write_text("id: x\n")
    result = runner.invoke(app, ["spec", "validate", str(bad)])
    assert result.exit_code != 0
    # Pydantic v2 ValidationError text mentions the missing fields.
    assert "validation error" in result.output.lower() or "field required" in result.output.lower()


def test_cli_spec_render__writes_deterministic_markdown(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    """WHEN `rigor spec render STUDY.yaml --out PATH.md` is invoked twice with same input,
    THEN both invocations produce byte-identical files and exit zero.
    """
    import hashlib

    from rigor.cli import app

    out1 = tmp_path / "spec1.md"
    out2 = tmp_path / "spec2.md"
    for out in (out1, out2):
        result = runner.invoke(
            app,
            [
                "spec", "render",
                str(repo_root / "studies" / "exhibit-a.yaml"),
                "--out", str(out),
                "--format", "markdown",
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists() and out.stat().st_size > 0

    h1 = hashlib.sha256(out1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(out2.read_bytes()).hexdigest()
    assert h1 == h2


def test_cli_spec_render__rejects_unsupported_format(
    runner: CliRunner, repo_root: Path, tmp_path: Path
) -> None:
    """WHEN `rigor spec render --format html` is invoked,
    THEN exit code is non-zero with a clear message naming the supported format.
    """
    from rigor.cli import app

    out = tmp_path / "spec.html"
    result = runner.invoke(
        app,
        [
            "spec", "render",
            str(repo_root / "studies" / "exhibit-a.yaml"),
            "--out", str(out),
            "--format", "html",
        ],
    )
    assert result.exit_code != 0
    assert "markdown" in result.output.lower()
