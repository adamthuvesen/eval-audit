"""Shared pytest fixtures and helpers for rigor tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def scouting_dir(repo_root: Path) -> Path:
    return repo_root / "scouting"
