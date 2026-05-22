"""Regression tests for source distribution hygiene."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path


def test_sdist__excludes_local_caches_and_build_outputs(repo_root: Path, tmp_path: Path) -> None:
    """The published sdist should contain source artifacts, not local machine state."""
    if shutil.which("uv") is None:
        raise AssertionError("uv is required to build eval-audit source distributions")

    result = subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(tmp_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

    sdists = sorted(tmp_path.glob("eval_audit-*.tar.gz"))
    assert len(sdists) == 1

    forbidden_roots = {
        ".agents",
        ".claude",
        ".codex",
        ".hypothesis",
        ".pytest_cache",
        ".ruff_cache",
        ".scout-cache",
        ".venv",
        "dist",
        "openspec",
        "worktrees",
    }
    forbidden_files = {".env", ".env.local"}

    with tarfile.open(sdists[0], "r:gz") as archive:
        leaked: list[str] = []
        for member in archive.getnames():
            path = Path(member)
            parts = path.parts
            if len(parts) < 2:
                continue
            root_entry = parts[1]
            if root_entry in forbidden_roots or root_entry in forbidden_files:
                leaked.append(member)

    assert leaked == []
