"""Shared pytest fixtures and helpers for eval-audit tests."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from eval_audit.schema import StudySpec


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


@pytest.fixture
def readiness_kwargs() -> Callable[[StudySpec, pl.DataFrame, Path], dict[str, str]]:
    """Build the (`evidence_readiness`, `check_sha256`) kwargs for `render_report`.

    Tests bypass the CLI's `check_paths` and call `check_evidence` directly,
    so the `study_loads` and `runs_load` checks here have empty `details`
    rather than the `path` keys a CLI run records on disk. The resulting
    `check_sha256` is therefore intentionally NOT byte-equal to the digest a
    user sees in `reports/<id>/check.json`. Snapshot byte-equality is what
    these tests pin.
    """
    from eval_audit.checks import check_evidence

    def _build(study: StudySpec, runs: pl.DataFrame, repo_root: Path) -> dict[str, str]:
        readiness = check_evidence(study, runs, repo_root=repo_root)
        return {
            "evidence_readiness": readiness.status,
            "check_sha256": hashlib.sha256(readiness.to_json_bytes()).hexdigest(),
        }

    return _build
