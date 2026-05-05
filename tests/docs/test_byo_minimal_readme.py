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


def test_project_readme__byo_section_exists_between_demo_and_quickstart(
    repo_root: Path,
) -> None:
    readme = (repo_root / "README.md").read_text()
    demo_idx = readme.index("## Demo reports")
    byo_idx = readme.index("## Bring your own data")
    quickstart_idx = readme.index("## Quickstart")
    assert demo_idx < byo_idx < quickstart_idx


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
