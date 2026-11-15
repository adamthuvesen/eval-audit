"""CI jobs call Make targets instead of copying their steps."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def test_ci_workflow__runs_only_make_targets(repo_root: Path) -> None:
    workflow = yaml.safe_load((repo_root / ".github/workflows/ci.yml").read_text())
    actual = {
        name: [step["run"] for step in job["steps"] if "run" in step]
        for name, job in workflow["jobs"].items()
    }
    assert workflow["jobs"]["slow"].get("needs") == "check", (
        "The slow job must declare `needs: check` so the fast lane runs first."
    )
    for name, runs in actual.items():
        setup = [
            run
            for run in runs[:-1]
            if run != "make setup" and not run.startswith("uv python install ")
        ]
        assert runs[-1] == f"make {name}" and not setup, (
            "CI jobs must run only Python install, `make setup`, then the Make target named for the job. "
            "Put new checks in the Makefile `check` or `slow` target, not in .github/workflows/ci.yml. "
            f"Got: {actual}"
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
    unpinned = [uses for uses in actions if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses)]
    assert not unpinned, (
        f"Pin every action in .github/workflows/ to a full 40-character commit SHA. Got: {unpinned}"
    )
    uv_versions = [
        str(step.get("with", {}).get("version", ""))
        for step in steps
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]
    assert uv_versions and all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in uv_versions), (
        f"Every setup-uv step must pin an exact uv `version:`. Got: {uv_versions}"
    )
