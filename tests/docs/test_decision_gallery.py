"""Anchor tests for the decision pattern gallery README sections and report."""

from __future__ import annotations

from pathlib import Path


def _gallery_section(readme: str) -> str:
    """Return the README's Decision pattern gallery section body."""
    start = readme.index("## Decision pattern gallery")
    end = readme.index("## Bring your own data")
    return readme[start:end]


def test_decision_gallery__readme_section_exists_with_synthetic_framing(
    repo_root: Path,
) -> None:
    """Section appears between Example reports and Bring your own data, and the
    body carries the literal substring `synthetic` so a future reader cannot
    mistake the gallery for benchmark evidence."""
    readme = (repo_root / "README.md").read_text()
    examples_idx = readme.index("## Example reports")
    gallery_idx = readme.index("## Decision pattern gallery")
    byo_idx = readme.index("## Bring your own data")
    assert examples_idx < gallery_idx < byo_idx

    section = _gallery_section(readme)
    assert "synthetic" in section.lower(), (
        "Decision pattern gallery section MUST carry the literal word `synthetic` "
        "so the gallery cannot be mistaken for benchmark evidence."
    )


def test_decision_gallery__readme_section_links_report_and_walkthrough(
    repo_root: Path,
) -> None:
    section = _gallery_section((repo_root / "README.md").read_text())
    assert "reports/decision-gallery/report.md" in section
    assert "examples/decision-gallery/README.md" in section


def test_decision_gallery__readme_section_names_verdict_tokens(
    repo_root: Path,
) -> None:
    """The section MUST name every verdict the gallery exercises so a future
    verdict change is caught."""
    section = _gallery_section((repo_root / "README.md").read_text())
    assert "hold" in section
    assert "rerun_more_n" in section
    # inconclusive_no_action is included in the current calibration; if a
    # future change drops the third claim, this assertion fails — at which
    # point the README section MUST be updated to match.
    assert "inconclusive_no_action" in section


def test_decision_gallery__example_readme_carries_synthetic_framing(
    repo_root: Path,
) -> None:
    walkthrough = (repo_root / "examples" / "decision-gallery" / "README.md").read_text()
    assert "synthetic" in walkthrough.lower()
    assert "reports/decision-gallery/report.md" in walkthrough


def test_decision_gallery__study_validates(repo_root: Path) -> None:
    """The gallery study MUST validate cleanly and carry id=decision-gallery."""
    from eval_audit.schema import StudySpec

    spec = StudySpec.from_yaml(repo_root / "studies" / "decision-gallery.yaml")
    assert spec.id == "decision-gallery"
    assert spec.schema_version == 1
    assert len(spec.claims) == 3


def test_decision_gallery__report_renders_targeted_verdicts(repo_root: Path) -> None:
    """The committed gallery report MUST contain a sub-stanza per claim
    naming each calibration target verdict in the Audit Summary."""
    report = (repo_root / "reports" / "decision-gallery" / "report.md").read_text()
    audit_summary_start = report.index("## Audit Summary")
    next_section = report.index("\n## ", audit_summary_start + 1)
    audit_summary = report[audit_summary_start:next_section]

    assert "### Claim `hold_pattern`" in audit_summary
    assert "`hold` —" in audit_summary  # verdict bullet for hold
    assert "### Claim `rerun_more_n_pattern`" in audit_summary
    assert "`rerun_more_n` —" in audit_summary
    assert "### Claim `inconclusive_no_action_pattern`" in audit_summary
    assert "`inconclusive_no_action` —" in audit_summary
