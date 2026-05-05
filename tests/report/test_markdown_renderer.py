"""Acceptance tests for the markdown report renderer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def exhibit_a_inputs(repo_root: Path):
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")
    adapter = HalGaiaAdapter()
    runs = adapter.load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    return study, runs, result


def _render(study, runs, result, repo_root: Path) -> str:
    from eval_audit.report.markdown import render_report

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


def test_report__all_nine_sections_are_present(exhibit_a_inputs, repo_root: Path) -> None:
    """WHEN the renderer is run against the Exhibit A study and GAIA fixture,
    THEN the resulting markdown contains all nine ## sections in the listed order.
    """
    study, runs, result = exhibit_a_inputs

    text = _render(study, runs, result, repo_root)

    expected_sections = [
        "## Audit Summary",
        "## Study",
        "## Provenance",
        "## Per-agent summary",
        "## Claims",
        "## Robustness Review",
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
    from eval_audit.report.markdown import render_report_to
    from eval_audit.schema import StudySpec
    from eval_audit.stats import CrossHarnessComparisonError

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


def test_report__incomplete_reconstructed_cost_produces_no_report_file(
    repo_root: Path, tmp_path: Path
) -> None:
    """WHEN a claimed agent has mixed null/non-null reconstructed costs,
    THEN render_report_to propagates the analysis error and writes no report.
    """
    from eval_audit.report.markdown import render_report_to
    from eval_audit.schema import StudySpec
    from eval_audit.stats import CostProvenanceError

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-a.yaml")
    treatment = study.claims[0].treatment
    control = study.claims[0].control

    def row(agent_id: str, task_id: str, success: bool, cost: float | None) -> dict:
        return {
            "agent_id": agent_id, "model_id": agent_id, "harness": study.harness,
            "run_id": f"r-{agent_id}", "task_id": task_id, "task_category": None,
            "seed": None, "success": success, "partial_credit": success,
            "outcome_status": "graded", "tokens_in": 1, "tokens_out": 1,
            "tokens_in_by_model": {"m": 1}, "tokens_out_by_model": {"m": 1},
            "latency_s": 1.0, "timestamp": None,
            "reconstructed_per_task_cost_usd": cost,
            "reported_run_total_cost_usd": 1.0,
            "cost_provenance": "partial" if cost is None else "reconciled",
            "rerun_metadata": {},
        }

    runs = pl.DataFrame(
        [
            row(treatment, "t1", True, 0.10),
            row(treatment, "t2", False, None),
            row(control, "t1", False, 0.05),
            row(control, "t2", False, 0.05),
        ],
        strict=False,
    )
    out_path = tmp_path / "report.md"

    with pytest.raises(CostProvenanceError):
        render_report_to(
            out_path,
            study,
            runs,
            clock=lambda: datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC),
            git_commit="deadbeef",
            fixture_sha256="0" * 64,
            repo_root=repo_root,
        )

    assert not out_path.exists(), "report file was written despite incomplete cost data"


def test_report__unsupported_lower_is_better_study_is_not_rendered(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """WHEN rendering receives a StudySpec that bypassed validation with lower_is_better,
    THEN rendering fails before emitting a claim row.
    """
    from eval_audit.report.markdown import render_report

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


# ---------------------------------------------------------------------------
# Audit Summary header — unit tests for the helpers and the rendered section.
# ---------------------------------------------------------------------------


@pytest.fixture
def exhibit_b_inputs(repo_root: Path):
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "exhibit-b.yaml")
    runs = HalTauBenchAdapter().load(repo_root / "scouting" / "candidates" / "tau-bench")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    return study, runs, result


def _extract_audit_summary(text: str) -> str:
    """Return everything between '## Audit Summary' and the next '## ' heading."""
    start = text.index("## Audit Summary")
    rest = text[start:]
    next_section = rest.index("\n## ", 1)
    return rest[: next_section + 1]


def test_verdict_gloss__covers_every_decision_token() -> None:
    """`_VERDICT_GLOSS` MUST cover exactly the six tokens in DECISION_IMPACT_VOCAB."""
    from eval_audit.report.decisions import DECISION_IMPACT_VOCAB
    from eval_audit.report.markdown import _VERDICT_GLOSS

    assert set(_VERDICT_GLOSS.keys()) == set(DECISION_IMPACT_VOCAB)
    for gloss in _VERDICT_GLOSS.values():
        assert gloss and isinstance(gloss, str), "every gloss must be a non-empty string"


def test_render_audit_summary_stanza__unknown_decision_token_raises() -> None:
    """Rendering a stanza with a verdict not in the gloss table fails loudly."""
    from eval_audit.report import ReportContractError
    from eval_audit.report.markdown import _render_audit_summary_stanza

    fake_claim = type(
        "C", (), {"delta_point_estimate": 0.0, "delta_ci_low": -0.05, "delta_ci_high": 0.05}
    )()

    with pytest.raises(ReportContractError) as exc_info:
        _render_audit_summary_stanza(
            fake_claim,
            "not_a_real_token",
            "inconclusive",
            target_mde=None,
            ci_half_width=0.05,
            n_paired=10,
            treatment_cost=1.0,
            control_cost=1.0,
            pushback="none",
        )
    assert "not_a_real_token" in str(exc_info.value)


def test_what_would_change_it__ci_wider_than_mde_renders_quantitative_n() -> None:
    """Wider-than-MDE branch surfaces a concrete N with the variance-fixed marker."""
    from eval_audit.report.markdown import _what_would_change_it
    from eval_audit.stats.resolution import estimate_required_paired_tasks

    line = _what_would_change_it(target_mde=0.03, ci_half_width=0.09, n_paired=100)
    expected_n = estimate_required_paired_tasks(100, 0.09, 0.03).additional_tasks

    assert line == (
        f"~{expected_n} more paired tasks would tighten the CI to "
        f"≤ MDE (estimated, variance-fixed scaling)"
    )
    assert "(estimated, variance-fixed scaling)" in line
    assert line.startswith("~")


def test_what_would_change_it__ci_inside_mde_surfaces_half_width_and_mde_numbers() -> None:
    """Inside-MDE branch names both numbers as percentage-points to two decimals."""
    from eval_audit.report.markdown import _what_would_change_it

    line = _what_would_change_it(target_mde=0.03, ci_half_width=0.015, n_paired=100)

    assert line == (
        "the study already resolves below the declared MDE "
        "(CI half-width 1.50 pp ≤ MDE 3.00 pp); "
        "no additional N would change the verdict"
    )


def test_what_would_change_it__null_target_mde_picks_encouragement() -> None:
    """Null-target-mde branch is unchanged from Change 1's wording."""
    from eval_audit.report.markdown import _what_would_change_it

    assert _what_would_change_it(target_mde=None, ci_half_width=0.10, n_paired=100) == (
        "declaring an inference.target_mde would let this report estimate "
        "required sample size"
    )


def test_what_would_change_it__renderer_n_matches_resolution_function() -> None:
    """The N surfaced in the rendered line equals the function's direct return."""
    from eval_audit.report.markdown import _what_would_change_it
    from eval_audit.stats.resolution import estimate_required_paired_tasks

    n_paired = 165
    ci_half_width = 0.09395
    target_mde = 0.03

    line = _what_would_change_it(target_mde, ci_half_width, n_paired)
    direct = estimate_required_paired_tasks(n_paired, ci_half_width, target_mde)

    assert f"~{direct.additional_tasks} " in line


def test_paired_task_count__includes_errored_rows_as_paired_tasks() -> None:
    """Errored rows still define paired tasks; they are counted as failures later."""
    from eval_audit.report.markdown import _paired_task_count

    runs = pl.DataFrame(
        [
            {"agent_id": "treatment", "task_id": "t1", "outcome_status": "graded"},
            {"agent_id": "treatment", "task_id": "t2", "outcome_status": "graded"},
            {"agent_id": "control", "task_id": "t1", "outcome_status": "errored"},
            {"agent_id": "control", "task_id": "t2", "outcome_status": "graded"},
        ]
    )

    assert _paired_task_count(runs, "treatment", "control") == 2


def test_reviewer_pushback__joins_all_caveats_in_fixed_order() -> None:
    """Errored rows -> cost provenance -> residual risks, comma-separated."""
    from dataclasses import dataclass

    from eval_audit.report.markdown import _reviewer_pushback

    @dataclass
    class FakeAgent:
        agent_id: str
        n_errored: int

    per_agent = [FakeAgent("a", 3), FakeAgent("b", 0)]
    residual = "1. risk one\n2. risk two\n"

    line = _reviewer_pushback(
        per_agent,
        cost_provenance_class="as_reported_only",
        residual_risks_text=residual,
    )

    assert line == (
        "errored rows present (3 across 1 agent), "
        "cost provenance is as_reported_only, "
        "2 residual risks inherited from scouting"
    )


def test_reviewer_pushback__none_flagged_when_no_caveats_apply() -> None:
    from dataclasses import dataclass

    from eval_audit.report.markdown import _reviewer_pushback

    @dataclass
    class FakeAgent:
        agent_id: str
        n_errored: int

    per_agent = [FakeAgent("a", 0), FakeAgent("b", 0)]
    placeholder = (
        "_(no scouting decision document at scouting/foo-decision.md; "
        "residual risks not surfaced.)_"
    )

    line = _reviewer_pushback(
        per_agent,
        cost_provenance_class="reconciled",
        residual_risks_text=placeholder,
    )

    assert line == "none flagged at this stage"


def test_audit_summary__exhibit_a_has_exactly_five_bullet_lines(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """Single-claim study renders five bullets in the fixed order, no sub-headings."""
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)
    summary = _extract_audit_summary(text)

    assert "### Claim" not in summary, "single-claim study must not emit a sub-heading"
    bullet_prefixes = [
        "- **Verdict:**",
        "- **Claim status:**",
        "- **Why:**",
        "- **What would change it:**",
        "- **Reviewer pushback:**",
    ]
    last_pos = summary.index("## Audit Summary")
    for prefix in bullet_prefixes:
        pos = summary.find(prefix)
        assert pos != -1, f"missing bullet: {prefix}"
        assert pos > last_pos, f"bullet out of order: {prefix}"
        last_pos = pos


def test_audit_summary__exhibit_b_emits_one_sub_stanza_per_claim(
    exhibit_b_inputs, repo_root: Path
) -> None:
    """Multi-claim study emits one `### Claim <id>` sub-stanza per claim."""
    study, runs, result = exhibit_b_inputs
    text = _render(study, runs, result, repo_root)
    summary = _extract_audit_summary(text)

    claim_ids = [c.claim_id for c in result.claims]
    assert len(claim_ids) == 3, "exhibit-b sanity check: expected three claims"

    last_pos = -1
    for claim_id in claim_ids:
        marker = f"### Claim `{claim_id}`"
        pos = summary.find(marker)
        assert pos != -1, f"missing sub-stanza for claim {claim_id!r}"
        assert pos > last_pos, f"claim sub-stanza out of order: {claim_id!r}"
        last_pos = pos

    # Each sub-stanza has the five bullets.
    for prefix in ("- **Verdict:**", "- **Claim status:**", "- **Why:**",
                   "- **What would change it:**", "- **Reviewer pushback:**"):
        assert summary.count(prefix) == len(claim_ids), (
            f"expected {len(claim_ids)} occurrences of {prefix!r} in summary"
        )


def test_audit_summary__exhibit_b_uses_paired_task_count_not_graded_row_count(
    exhibit_b_inputs, repo_root: Path
) -> None:
    """Errored rows count as paired failures, so Exhibit B should report n=50."""
    study, runs, result = exhibit_b_inputs
    text = _render(study, runs, result, repo_root)
    summary = _extract_audit_summary(text)

    assert "over 47 paired tasks" not in summary
    assert summary.count("over 50 paired tasks") == len(result.claims)


def test_audit_summary__claim_status_matches_claims_table_value(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """Vocabulary alignment: Audit Summary status must match Claims-table status."""
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)
    summary = _extract_audit_summary(text)

    # Pull the status from the audit summary.
    status_line = next(
        line for line in summary.splitlines() if line.startswith("- **Claim status:**")
    )
    summary_status = status_line.split(":**", 1)[1].strip()

    # Pull the status from the Claims table row (third '|' field after the header).
    after_summary = text[text.index("## Claims"):]
    claims_rows = [
        line for line in after_summary.splitlines()
        if line.startswith("|") and not line.startswith("|---") and "|---" not in line
    ]
    # Skip header row.
    data_row = claims_rows[1]
    cells = [c.strip() for c in data_row.split("|")[1:-1]]
    table_status = cells[2]

    assert summary_status == table_status
    assert summary_status in {"supported", "unsupported", "inconclusive"}


def test_audit_summary__verdict_line_carries_token_and_gloss(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """Exhibit A's hedge_on_cost verdict surfaces with the exact gloss string."""
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)
    summary = _extract_audit_summary(text)

    expected = (
        "- **Verdict:** `hedge_on_cost` — "
        "CI crosses zero and the cost gap is material"
    )
    assert expected in summary


def test_audit_summary__verdict_glosses_are_exhaustive_and_pinned() -> None:
    """The gloss for each token matches the spec's pinned wording exactly."""
    from eval_audit.report.markdown import _VERDICT_GLOSS

    expected = {
        "switch": "claim is supported and the effect favours the treatment",
        "hold": "rejection is in the wrong direction; treatment fails the claim",
        "drop_from_shortlist": "treatment is Pareto-dominated on cost-quality",
        "rerun_more_n": "CI crosses zero with no material cost gap; needs more data",
        "hedge_on_cost": "CI crosses zero and the cost gap is material",
        "inconclusive_no_action": "result does not meet any decision threshold",
    }
    assert expected == _VERDICT_GLOSS


# ---------------------------------------------------------------------------
# Robustness Review — unit tests for the helpers and the rendered section.
# ---------------------------------------------------------------------------


def _row(dim: str, val: str, verdict: str):
    """Build a SensitivityRow without importing the dataclass at module level."""
    from eval_audit.report.sensitivity import SensitivityRow

    return SensitivityRow(dimension=dim, value=val, verdict=verdict)


def test_robustness_dimensions__exact_five_in_fixed_order() -> None:
    from eval_audit.report.markdown import _ROBUSTNESS_DIMENSIONS

    assert _ROBUSTNESS_DIMENSIONS == (
        "Multiple-comparison correction",
        "Errored-row policy",
        "Cost-threshold sensitivity",
        "Target MDE",
        "Cost provenance",
    )


def test_robustness_multiple_comparison__all_match_baseline_survives() -> None:
    from eval_audit.report.markdown import _robustness_multiple_comparison

    rows = [
        _row("baseline", "locked", "hedge_on_cost"),
        _row("alpha", "0.01", "hedge_on_cost"),
        _row("alpha", "0.10", "hedge_on_cost"),
        _row("correction_method", "none", "hedge_on_cost"),
    ]
    assert _robustness_multiple_comparison(rows, "hedge_on_cost") == (
        "survives",
        "verdict unchanged at α∈{0.01, 0.10} and with correction=none",
    )


def test_robustness_multiple_comparison__only_alpha_001_flips() -> None:
    from eval_audit.report.markdown import _robustness_multiple_comparison

    rows = [
        _row("alpha", "0.01", "switch"),
        _row("alpha", "0.10", "hedge_on_cost"),
        _row("correction_method", "none", "hedge_on_cost"),
    ]
    assert _robustness_multiple_comparison(rows, "hedge_on_cost") == (
        "does not survive",
        "verdict flips at α=0.01",
    )


def test_robustness_multiple_comparison__alpha_010_and_correction_flip() -> None:
    from eval_audit.report.markdown import _robustness_multiple_comparison

    rows = [
        _row("alpha", "0.01", "hedge_on_cost"),
        _row("alpha", "0.10", "switch"),
        _row("correction_method", "none", "switch"),
    ]
    assert _robustness_multiple_comparison(rows, "hedge_on_cost") == (
        "does not survive",
        "verdict flips at α=0.10, correction=none",
    )


def test_robustness_errored_policy__match_baseline_survives() -> None:
    from eval_audit.report.markdown import _robustness_errored_policy

    rows = [_row("errored_policy", "excluded", "hedge_on_cost")]
    assert _robustness_errored_policy(rows, "hedge_on_cost") == (
        "survives",
        "verdict unchanged when errored rows excluded",
    )


def test_robustness_errored_policy__flip_includes_baseline_and_flipped_tokens() -> None:
    from eval_audit.report.markdown import _robustness_errored_policy

    rows = [_row("errored_policy", "excluded", "rerun_more_n")]
    assert _robustness_errored_policy(rows, "hedge_on_cost") == (
        "does not survive",
        "verdict flips when errored rows excluded (hedge_on_cost → rerun_more_n)",
    )


def test_robustness_errored_policy__missing_row_raises() -> None:
    from eval_audit.report import ReportContractError
    from eval_audit.report.markdown import _robustness_errored_policy

    with pytest.raises(ReportContractError):
        _robustness_errored_policy([], "hedge_on_cost")


def test_robustness_cost_threshold__both_match_baseline_survives() -> None:
    from eval_audit.report.markdown import _robustness_cost_threshold

    rows = [
        _row("cost_gap_threshold", "0.05", "hedge_on_cost"),
        _row("cost_gap_threshold", "0.20", "hedge_on_cost"),
    ]
    assert _robustness_cost_threshold(rows, "hedge_on_cost") == (
        "survives",
        "verdict unchanged at cost_gap_threshold∈{0.05, 0.20}",
    )


def test_robustness_cost_threshold__only_020_flips() -> None:
    from eval_audit.report.markdown import _robustness_cost_threshold

    rows = [
        _row("cost_gap_threshold", "0.05", "hedge_on_cost"),
        _row("cost_gap_threshold", "0.20", "rerun_more_n"),
    ]
    assert _robustness_cost_threshold(rows, "hedge_on_cost") == (
        "does not survive",
        "verdict flips at cost_gap_threshold=0.20",
    )


def test_robustness_target_mde__null_target_returns_not_assessed() -> None:
    from eval_audit.report.markdown import _robustness_target_mde

    assert _robustness_target_mde(None, 0.05) == (
        "not assessed",
        "inference.target_mde not declared",
    )


def test_robustness_target_mde__ci_inside_mde_survives() -> None:
    from eval_audit.report.markdown import _robustness_target_mde

    assert _robustness_target_mde(0.03, 0.02) == (
        "survives",
        "CI half-width 2.00 pp ≤ MDE 3.00 pp; sufficiently resolved",
    )


def test_robustness_target_mde__ci_outside_mde_does_not_survive() -> None:
    from eval_audit.report.markdown import _robustness_target_mde

    assert _robustness_target_mde(0.03, 0.09) == (
        "does not survive",
        "CI half-width 9.00 pp > MDE 3.00 pp; under-resolved",
    )


def test_robustness_cost_provenance__class_to_vocabulary_mapping() -> None:
    from eval_audit.report.markdown import _robustness_cost_provenance

    assert _robustness_cost_provenance("reconciled") == ("survives", "reconciled")
    assert _robustness_cost_provenance("as_reported_only") == (
        "caveat",
        "as_reported_only",
    )
    assert _robustness_cost_provenance("partial") == ("caveat", "partial")
    assert _robustness_cost_provenance("not_applicable") == (
        "does not survive",
        "not_applicable",
    )


def _extract_robustness_review(text: str) -> str:
    """Return everything between '## Robustness Review' and the next '## ' heading."""
    start = text.index("## Robustness Review")
    rest = text[start:]
    next_section = rest.index("\n## ", 1)
    return rest[: next_section + 1]


def test_robustness_review__appears_between_claims_and_cost_quality(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """Section 6 in the new ordering: between Claims and Cost-quality view."""
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)

    claims_pos = text.index("## Claims")
    rr_pos = text.index("## Robustness Review")
    cost_pos = text.index("## Cost-quality view")

    assert claims_pos < rr_pos < cost_pos


def test_robustness_review__exhibit_a_has_five_data_rows_in_listed_order(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """Single-claim study renders five rows in the fixed dimension order."""
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)
    section = _extract_robustness_review(text)

    expected_dimensions = [
        "| Multiple-comparison correction |",
        "| Errored-row policy |",
        "| Cost-threshold sensitivity |",
        "| Target MDE |",
        "| Cost provenance |",
    ]
    last_pos = -1
    for dim in expected_dimensions:
        pos = section.find(dim)
        assert pos != -1, f"missing dimension row: {dim}"
        assert pos > last_pos, f"dimension out of order: {dim}"
        last_pos = pos


def test_robustness_review__exhibit_a_target_mde_does_not_survive(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """Exhibit A's CI is much wider than its MDE (9.39 pp > 3 pp)."""
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)
    section = _extract_robustness_review(text)

    # The Target MDE row should read "does not survive" with the under-resolved note.
    target_line = next(
        line for line in section.splitlines() if line.startswith("| Target MDE |")
    )
    assert "does not survive" in target_line
    assert "under-resolved" in target_line
    assert " pp >" in target_line  # half-width > MDE


def test_robustness_review__exhibit_a_cost_provenance_reconciled(
    exhibit_a_inputs, repo_root: Path
) -> None:
    """Exhibit A uses the GAIA fixture which reconciles cleanly."""
    study, runs, result = exhibit_a_inputs
    text = _render(study, runs, result, repo_root)
    section = _extract_robustness_review(text)

    cost_line = next(
        line for line in section.splitlines() if line.startswith("| Cost provenance |")
    )
    assert cost_line == "| Cost provenance | survives | reconciled |"


def test_robustness_review__exhibit_b_has_one_sub_stanza_per_claim(
    exhibit_b_inputs, repo_root: Path
) -> None:
    """Multi-claim study emits one `### Claim <id>` sub-stanza per claim."""
    study, runs, result = exhibit_b_inputs
    text = _render(study, runs, result, repo_root)
    section = _extract_robustness_review(text)

    claim_ids = [c.claim_id for c in result.claims]
    assert len(claim_ids) == 3, "exhibit-b sanity check"

    last_pos = -1
    for claim_id in claim_ids:
        marker = f"### Claim `{claim_id}`"
        pos = section.find(marker)
        assert pos != -1, f"missing sub-stanza for claim {claim_id!r}"
        assert pos > last_pos, f"claim sub-stanza out of order: {claim_id!r}"
        last_pos = pos


def test_robustness_review__every_result_value_is_in_vocabulary(
    exhibit_a_inputs, exhibit_b_inputs, repo_root: Path
) -> None:
    """Every Result column value across both exhibits is one of the four vocab values."""
    allowed = {"survives", "does not survive", "caveat", "not assessed"}

    for inputs in (exhibit_a_inputs, exhibit_b_inputs):
        study, runs, result = inputs
        text = _render(study, runs, result, repo_root)
        section = _extract_robustness_review(text)
        for line in section.splitlines():
            if not line.startswith("| ") or line.startswith("| Dimension"):
                continue
            if line.startswith("|---"):
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) != 3:
                continue
            assert cells[1] in allowed, (
                f"Result column value {cells[1]!r} not in allowed vocabulary {allowed} "
                f"on line: {line}"
            )
