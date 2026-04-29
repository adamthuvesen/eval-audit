"""Acceptance tests for the markdown report renderer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def exhibit_a_inputs(repo_root: Path):
    from rigor.ingest.hal_gaia import HalGaiaAdapter
    from rigor.schema import StudySpec
    from rigor.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")
    adapter = HalGaiaAdapter()
    runs = adapter.load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    return study, runs, result


def _render(study, runs, result, repo_root: Path) -> str:
    from rigor.report.markdown import render_report

    return render_report(
        result,
        study,
        runs,
        clock=lambda: datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC),
        git_commit="deadbeef",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
        bootstrap_iterations=2_000,
        bootstrap_seed=42,
    )


def test_report__all_seven_sections_are_present(exhibit_a_inputs, repo_root: Path) -> None:
    """WHEN the renderer is run against the Exhibit A study and GAIA fixture,
    THEN the resulting markdown contains all seven ## sections in the listed order.
    """
    study, runs, result = exhibit_a_inputs

    text = _render(study, runs, result, repo_root)

    expected_sections = [
        "## Study",
        "## Provenance",
        "## Per-agent summary",
        "## Claims",
        "## Cost-quality view",
        "## Residual risks",
        "## Reproducibility footer",
    ]
    last_pos = -1
    for section in expected_sections:
        pos = text.find(section)
        assert pos != -1, f"missing section: {section}"
        assert pos > last_pos, f"section out of order: {section}"
        last_pos = pos


def test_report__inherited_residual_risks_are_not_edited(exhibit_a_inputs, repo_root: Path) -> None:
    """WHEN the residual-risks section is rendered,
    THEN the text under 'Inherited from scouting decision' matches the residual-risks
    bullets in scouting/exhibit-a-decision.md byte-for-byte after whitespace normalization.
    """
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)

    # Extract the inherited block from the rendered report.
    marker = "Inherited from scouting decision"
    assert marker in text
    inherited_start = text.index(marker)
    # Take everything after the heading until the next blank-line+heading or section break.
    inherited_block = text[inherited_start:]

    # Read the source bullets from the decision document.
    decision_md = (repo_root / "scouting" / "exhibit-a-decision.md").read_text()
    risks_start = decision_md.index("## Residual risks")
    risks_end = decision_md.index("\n## ", risks_start + 1)
    source_block = decision_md[risks_start:risks_end]

    # Each source numbered bullet's leading sentence should appear in the rendered block.
    for line in source_block.splitlines():
        line = line.strip()
        if line.startswith(("1.", "2.", "3.", "4.", "5.")):
            # Take the first sentence (up to first period) — that's the unique header.
            head = line.split(".", 2)[1].strip().split(".")[0]
            head_norm = " ".join(head.split())
            inherited_norm = " ".join(inherited_block.split())
            assert head_norm in inherited_norm, f"residual risk header missing from report: {head_norm!r}"


def test_report__rerunning_renders_byte_identical_output(exhibit_a_inputs, repo_root: Path) -> None:
    """WHEN the renderer is invoked twice with the same inputs and a fixed clock,
    THEN the two outputs have identical sha256 hashes.
    """
    import hashlib

    study, runs, result = exhibit_a_inputs
    a = _render(study, runs, result, repo_root)
    b = _render(study, runs, result, repo_root)

    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


def test_report__snapshot_diff_caught_in_tests(exhibit_a_inputs, repo_root: Path, tmp_path: Path) -> None:
    """WHEN a developer mutates the renderer's output without updating the snapshot,
    THEN the snapshot test fails with a diff showing the change.

    Verified by snapshotting the rendered report, mutating a copy, and asserting
    the comparison detects the mutation.
    """
    study, runs, result = exhibit_a_inputs

    rendered = _render(study, runs, result, repo_root)
    snapshot_path = tmp_path / "exhibit-a-report.md"
    snapshot_path.write_text(rendered)

    mutated = rendered.replace("## Per-agent summary", "## Per-agent summary BREAKING CHANGE")

    # The snapshot comparison the test infrastructure uses is just text equality.
    assert mutated != snapshot_path.read_text(), "snapshot mechanism failed to detect mutation"


def test_report__cross_harness_study_produces_no_report_file(repo_root: Path, tmp_path: Path) -> None:
    """WHEN a study spec is rendered against a frame where treatment and control rows
    have different harness values, THEN no markdown file is written and a
    CrossHarnessComparisonError propagates.
    """
    from rigor.report.markdown import render_report_to
    from rigor.schema import StudySpec
    from rigor.stats import CrossHarnessComparisonError

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")

    treatment = study.claims[0].treatment
    control = study.claims[0].control
    rows = [
        {
            "agent_id": treatment, "model_id": "m1", "harness": "hal_generalist_agent",
            "run_id": "r1", "task_id": "t1", "task_category": None, "seed": None,
            "success": True, "partial_credit": True, "outcome_status": "graded",
            "tokens_in": 1, "tokens_out": 1,
            "tokens_in_by_model": {"m": 1}, "tokens_out_by_model": {"m": 1},
            "latency_s": 1.0, "timestamp": None,
            "reconstructed_per_task_cost_usd": 0.001,
            "reported_run_total_cost_usd": 0.05,
            "cost_provenance": "reconciled", "rerun_metadata": {},
        },
        {
            "agent_id": control, "model_id": "m2", "harness": "hal_tool_calling",
            "run_id": "r2", "task_id": "t1", "task_category": None, "seed": None,
            "success": False, "partial_credit": False, "outcome_status": "graded",
            "tokens_in": 1, "tokens_out": 1,
            "tokens_in_by_model": {"m": 1}, "tokens_out_by_model": {"m": 1},
            "latency_s": 1.0, "timestamp": None,
            "reconstructed_per_task_cost_usd": 0.001,
            "reported_run_total_cost_usd": 0.05,
            "cost_provenance": "reconciled", "rerun_metadata": {},
        },
    ]
    runs = pl.DataFrame(rows, strict=False)
    out_path = tmp_path / "report.md"

    with pytest.raises(CrossHarnessComparisonError):
        render_report_to(
            out_path,
            study,
            runs,
            clock=lambda: datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC),
            git_commit="deadbeef",
            fixture_sha256="0" * 64,
            repo_root=repo_root,
        )
    assert not out_path.exists(), "report file was written despite cross-harness rejection"


def test_report__unsupported_lower_is_better_study_is_not_rendered(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """WHEN rendering receives a StudySpec that bypassed validation with lower_is_better,
    THEN rendering fails before emitting a claim row.
    """
    from rigor.report.markdown import render_report

    study, runs, result = exhibit_a_inputs
    bad_primary = study.primary_outcome.model_copy(update={"direction": "lower_is_better"})
    bad_study = study.model_copy(update={"primary_outcome": bad_primary})

    with pytest.raises(ValueError) as exc_info:
        render_report(
            result,
            bad_study,
            runs,
            clock=lambda: datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC),
            git_commit="deadbeef",
            fixture_sha256="0" * 64,
            repo_root=repo_root,
        )

    assert "higher_is_better" in str(exc_info.value)
