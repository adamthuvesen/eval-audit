"""Anchor tests for the BYO worked-example narrative and the project README's BYO section."""

from __future__ import annotations

from pathlib import Path


def test_byo_minimal_readme__not_a_stub(repo_root: Path) -> None:
    """Light guard against the worked example README rotting back to a stub."""
    readme = (repo_root / "examples" / "byo-minimal" / "README.md").read_text()
    word_count = len(readme.split())
    assert word_count >= 150, (
        f"examples/byo-minimal/README.md has only {word_count} words; "
        "expected a worked walkthrough of >=150 words"
    )


def test_byo_minimal_readme__links_to_input_contract(repo_root: Path) -> None:
    readme = (repo_root / "examples" / "byo-minimal" / "README.md").read_text()
    assert "INPUT_CONTRACT.md" in readme


def test_byo_minimal_readme__links_to_rendered_report(repo_root: Path) -> None:
    readme = (repo_root / "examples" / "byo-minimal" / "README.md").read_text()
    assert "byo-minimal/report.md" in readme


def test_byo_minimal_readme__mentions_switch_verdict(repo_root: Path) -> None:
    readme = (repo_root / "examples" / "byo-minimal" / "README.md").read_text()
    assert "switch" in readme


def test_byo_minimal_readme__mentions_make_runs(repo_root: Path) -> None:
    readme = (repo_root / "examples" / "byo-minimal" / "README.md").read_text()
    assert "make_runs.py" in readme


# ---------------------------------------------------------------------------
# Project README "Bring your own data" section anchors
# ---------------------------------------------------------------------------


def test_project_readme__byo_section_exists_between_examples_and_quickstart(
    repo_root: Path,
) -> None:
    readme = (repo_root / "README.md").read_text()
    demo_idx = readme.index("## Demo reports")
    examples_idx = readme.index("## Example reports")
    byo_idx = readme.index("## Bring your own data")
    quickstart_idx = readme.index("## Quickstart")
    assert demo_idx < examples_idx < byo_idx < quickstart_idx


def test_project_readme__example_reports_section_indexes_three_reports(
    repo_root: Path,
) -> None:
    """The Example reports gallery MUST list the three committed reports with
    their verdict tokens spelled out, so a future verdict change is caught."""
    readme = (repo_root / "README.md").read_text()
    examples_idx = readme.index("## Example reports")
    next_idx = readme.index("## Bring your own data")
    section = readme[examples_idx:next_idx]

    # Three committed reports, each as a markdown link.
    assert "reports/exhibit-a/report.md" in section
    assert "reports/exhibit-b/report.md" in section
    assert "reports/byo-minimal/report.md" in section

    # Verdict tokens named literally for each report.
    assert "hedge_on_cost" in section  # exhibit-a (also exhibit-b ×2)
    assert "drop_from_shortlist" in section  # exhibit-b
    assert "switch" in section  # byo-minimal


def test_project_readme__byo_section_links_input_contract_and_example(
    repo_root: Path,
) -> None:
    readme = (repo_root / "README.md").read_text()
    byo_idx = readme.index("## Bring your own data")
    next_idx = readme.index("## Quickstart")
    section = readme[byo_idx:next_idx]
    assert "agents/docs/INPUT_CONTRACT.md" in section
    assert "agents/docs/STUDY_SCHEMA.md" in section
    assert "examples/byo-minimal/README.md" in section


def test_project_readme__byo_section_shows_canonical_cli_snippet(
    repo_root: Path,
) -> None:
    readme = (repo_root / "README.md").read_text()
    byo_idx = readme.index("## Bring your own data")
    next_idx = readme.index("## Quickstart")
    section = readme[byo_idx:next_idx]
    assert "eval-audit init" in section
    assert "eval-audit validate" in section
    assert "eval-audit analyze" in section
