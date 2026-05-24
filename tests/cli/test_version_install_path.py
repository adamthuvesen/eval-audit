"""Regression tests pinning the install-path contract for `eval-audit --version`.

The repo's existing tests/cli/test_version.py exercises `--version` in-process via
Typer's CliRunner. The tests here add two install-path guarantees:

1. The CLI works when invoked as a subprocess (through the installed console
   script), not just in-process — this is the closest in-pytest proxy for the
   `uv tool install` path the spec requires.
2. No hardcoded version constant duplicates `pyproject.toml`'s `[project].version`
   field. The single source of truth is package metadata, surfaced via
   `importlib.metadata`.

See openspec/specs/cli/spec.md → "Top-level --version flag prints the package
version" (the install-path scenarios) and openspec/specs/release-engineering/spec.md
→ "Package is installable via uv tool install / pipx and the CLI resolves its
version".
"""

from __future__ import annotations

import importlib.metadata
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_version_install_path__subprocess_prints_metadata_version() -> None:
    """Invoking the installed console script via subprocess prints the package version.

    Uses ``python -m eval_audit.cli`` rather than the bare ``eval-audit`` binary so
    the test does not depend on PATH ordering inside the dev environment. The
    behaviour exercised — Typer's eager --version callback resolving via
    ``importlib.metadata`` — is identical regardless of how the CLI is invoked.
    """
    expected = importlib.metadata.version("eval-audit")
    result = subprocess.run(
        [sys.executable, "-m", "eval_audit.cli", "--version"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{expected}\n", (
        f"expected {expected!r} + newline, got {result.stdout!r}"
    )


def test_version_install_path__no_hardcoded_version_constant_in_source() -> None:
    """The single source of truth for the version is pyproject.toml.

    A future cleanup that re-adds a hardcoded ``__version__ = "1.x.y"`` constant
    in source (or any equivalent literal duplicating ``pyproject.toml``'s
    ``[project].version``) would make ``--version`` resolve incorrectly under a
    packaged install where the wheel's metadata is the only authoritative source.
    Catch the regression at test time, not at install time.
    """
    expected = importlib.metadata.version("eval-audit")
    # Match the literal version string assigned in source (allow either single or
    # double quotes). Anchor to assignment-style usage so unrelated string mentions
    # in docstrings or comments don't trip the test.
    pattern = re.compile(
        r"""(__version__|VERSION)\s*=\s*['"]""" + re.escape(expected) + r"""['"]"""
    )
    offenders: list[str] = []
    for path in (REPO_ROOT / "eval_audit").rglob("*.py"):
        text = path.read_text()
        if pattern.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"hardcoded version constant matching {expected!r} found in: {offenders}. "
        "The single source of truth is pyproject.toml; resolve via importlib.metadata."
    )


def test_version_install_path__init_exposes_metadata_backed_dunder_version() -> None:
    """`eval_audit.__version__` resolves to the package metadata version.

    Some downstream tooling reads ``package.__version__`` directly. Pin that the
    attribute is metadata-backed so it stays in sync with ``--version`` and the
    wheel's reported version under any install path.
    """
    import eval_audit

    expected = importlib.metadata.version("eval-audit")
    assert eval_audit.__version__ == expected
