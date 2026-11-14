"""CI jobs call Make targets instead of copying their steps."""

from __future__ import annotations

import re
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


def test_ci_workflow__pins_actions_and_uv_exactly(repo_root: Path) -> None:
    workflows = sorted((repo_root / ".github/workflows").glob("*.y*ml"))
    steps = [
        step
        for path in workflows
        for job in yaml.safe_load(path.read_text())["jobs"].values()
        for step in job.get("steps", [])
    ]
    actions = [step["uses"] for step in steps if "uses" in step]
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses) for uses in actions), actions
    uv_versions = [
        str(step.get("with", {}).get("version", ""))
        for step in steps
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]
    assert uv_versions and all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in uv_versions), (
        f"Every setup-uv step must pin an exact uv `version:`. Got: {uv_versions}"
    )
