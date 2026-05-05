"""Shared pytest fixtures and helpers for eval-audit tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def scouting_dir(repo_root: Path) -> Path:
    return repo_root / "scouting"


@pytest.fixture(scope="session", autouse=True)
def _ensure_example_fixtures(repo_root: Path) -> None:
    """Regenerate gitignored example parquet fixtures at session start when missing.

    The committed `make_runs.py` scripts under `examples/<name>/` are the
    source of truth for the toy parquet fixtures; the parquet files
    themselves are gitignored. On a fresh checkout (CI included) the parquets
    do not exist until `make_runs.py` runs. Several tests reference these
    parquets directly, so we auto-regenerate them here rather than coupling
    every test to a per-test setup hook.
    """
    examples = (
        repo_root / "examples" / "byo-minimal",
        repo_root / "examples" / "decision-gallery",
    )
    for example_dir in examples:
        parquet = example_dir / "runs.parquet"
        if parquet.exists():
            continue
        script = example_dir / "make_runs.py"
        if not script.exists():
            continue
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(example_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"failed to regenerate {parquet} via {script}:\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
