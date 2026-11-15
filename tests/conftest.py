"""Shared pytest fixtures and helpers for eval-audit tests."""

from __future__ import annotations

import hashlib
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


@pytest.fixture
def readiness_kwargs() -> Callable[..., dict[str, str]]:
    """Build the (`evidence_readiness`, `check_sha256`) kwargs for `render_report`.

    Tests bypass the CLI's `check_paths` and call `check_evidence` directly,
    so the `study_loads` and `runs_load` checks here have empty `details`
    rather than the `path` keys a CLI run records on disk. The resulting
    `check_sha256` is therefore intentionally NOT byte-equal to the digest a
    user sees in `reports/<id>/check.json`.
    """
    from eval_audit.checks import check_evidence
    from eval_audit.evidence_types import EvidenceSource

    def _build(
        study: StudySpec, runs: pl.DataFrame, repo_root: Path, source: EvidenceSource | None = None
    ) -> dict[str, str]:
        readiness = check_evidence(study, runs, repo_root=repo_root, source=source)
        return {
            "evidence_readiness": readiness.status,
            "check_sha256": hashlib.sha256(readiness.to_json_bytes()).hexdigest(),
        }

    return _build
