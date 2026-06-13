"""Anchor tests for the BYO worked-example narrative and the project README's BYO section."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def byo_readme(repo_root: Path) -> str:
    return (repo_root / "examples" / "byo-minimal" / "README.md").read_text()


@pytest.fixture(scope="module")
def project_readme(repo_root: Path) -> str:
    return (repo_root / "README.md").read_text()


def test_byo_minimal_readme__not_a_stub(byo_readme: str) -> None:
    """Light guard against the worked example README rotting back to a stub."""
    word_count = len(byo_readme.split())
    assert word_count >= 150, (
        f"examples/byo-minimal/README.md has only {word_count} words; "
        "expected a worked walkthrough of >=150 words"
    )


def test_byo_minimal_readme__links_to_input_contract(byo_readme: str) -> None:
    assert "INPUT_CONTRACT.md" in byo_readme


def test_byo_minimal_readme__links_to_rendered_report(byo_readme: str) -> None:
    assert "byo-minimal/report.md" in byo_readme


def test_byo_minimal_readme__mentions_switch_verdict(byo_readme: str) -> None:
    assert "switch" in byo_readme


def test_byo_minimal_readme__mentions_make_runs(byo_readme: str) -> None:
    assert "make_runs.py" in byo_readme


# ---------------------------------------------------------------------------
# Project README "Bring your own data" section anchors
# ---------------------------------------------------------------------------


def test_project_readme__byo_section_exists_between_examples_and_quickstart(
    project_readme: str,
) -> None:
    demo_idx = project_readme.index("## Demo reports")
    examples_idx = project_readme.index("## Example reports")
    byo_idx = project_readme.index("## Bring your own data")
    quickstart_idx = project_readme.index("## Quickstart")
    assert demo_idx < examples_idx < byo_idx < quickstart_idx


def test_project_readme__example_reports_section_indexes_three_reports(
    project_readme: str,
) -> None:
    """The Example reports gallery MUST list the three committed reports with
    their verdict tokens spelled out, so a future verdict change is caught."""
    examples_idx = project_readme.index("## Example reports")
    next_idx = project_readme.index("## Bring your own data")
    section = project_readme[examples_idx:next_idx]

    # Three committed reports, each as a markdown link.
    assert "reports/gaia-hal-generalist/report.md" in section
    assert "reports/tau-bench-airline-tool-calling/report.md" in section
    assert "reports/byo-minimal/report.md" in section

    # Verdict tokens named literally for each report.
    assert (
        "hedge_on_cost" in section
    )  # gaia-hal-generalist (also tau-bench-airline-tool-calling ×2)
    assert "drop_from_shortlist" in section  # tau-bench-airline-tool-calling
    assert "switch" in section  # byo-minimal


def test_project_readme__byo_section_links_input_contract_and_example(
    project_readme: str,
) -> None:
    byo_idx = project_readme.index("## Bring your own data")
    next_idx = project_readme.index("## Quickstart")
    section = project_readme[byo_idx:next_idx]
    assert "docs/INPUT_CONTRACT.md" in section
    assert "docs/STUDY_SCHEMA.md" in section
    assert "examples/byo-minimal/README.md" in section


def test_project_readme__byo_section_shows_canonical_cli_snippet(
    project_readme: str,
) -> None:
    byo_idx = project_readme.index("## Bring your own data")
    next_idx = project_readme.index("## Quickstart")
    section = project_readme[byo_idx:next_idx]
    assert "eval-audit init" in section
    assert "eval-audit validate" in section
    assert "eval-audit check" in section
    assert "eval-audit analyze" in section
    assert section.index("eval-audit validate") < section.index("eval-audit check")
    assert section.index("eval-audit check") < section.index("eval-audit report")


def test_project_readme__distinguishes_validate_from_check(
    project_readme: str,
) -> None:
    normalized = " ".join(project_readme.split())
    assert "`validate` checks the input schemas" in normalized
    assert "`check` evaluates whether the declared comparison is audit-ready" in normalized


def test_byo_minimal_readme__runs_check_before_report(byo_readme: str) -> None:
    assert "eval-audit check" in byo_readme
    assert byo_readme.index("eval-audit check") < byo_readme.index("eval-audit report")
