"""CI jobs call Make targets instead of copying their steps."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_ci_workflow__runs_only_make_targets(repo_root: Path) -> None:
    workflow = yaml.safe_load((repo_root / ".github/workflows/ci.yml").read_text())
    setup = ["uv python install 3.14", "make setup"]
    expected = {"check": [*setup, "make check"], "slow": [*setup, "make slow"]}
    actual = {
        name: [step["run"] for step in job["steps"] if "run" in step]
        for name, job in workflow["jobs"].items()
    }
    assert workflow["jobs"]["slow"].get("needs") == "check", (
        "The slow job must declare `needs: check` so the fast lane runs first."
    )
    assert actual == expected, (
        "CI jobs must run only Python install, `make setup`, then one Make target. Put new checks in the "
        f"Makefile `check` or `slow` target, not in .github/workflows/ci.yml. Got: {actual}"
    )
