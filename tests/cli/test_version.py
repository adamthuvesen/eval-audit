"""Tests for the top-level `eval-audit --version` flag."""

from __future__ import annotations

import importlib.metadata

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_version__prints_package_version_and_exits_zero(runner: CliRunner) -> None:
    """`eval-audit --version` prints exactly the importlib.metadata version + newline."""
    from eval_audit.cli import app

    result = runner.invoke(app, ["--version"])

    expected = importlib.metadata.version("eval-audit")
    assert result.exit_code == 0
    assert result.output == f"{expected}\n"


def test_version__does_not_invoke_subcommand(runner: CliRunner) -> None:
    """`--version` is eager and exits before any subcommand parsing."""
    from eval_audit.cli import app

    # Pair --version with a bogus subcommand. Eager exit means the bogus
    # subcommand is never reached.
    result = runner.invoke(app, ["--version", "not-a-real-command"])

    assert result.exit_code == 0
    expected = importlib.metadata.version("eval-audit")
    assert result.output == f"{expected}\n"
