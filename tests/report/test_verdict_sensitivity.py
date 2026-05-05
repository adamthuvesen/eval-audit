"""Acceptance tests for the Verdict sensitivity sub-block."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

FIXED_CLOCK = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def gaia_hal_generalist(repo_root: Path):
    from eval_audit.ingest.hal_gaia import HalGaiaAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "gaia-hal-generalist.yaml")
    runs = HalGaiaAdapter().load(repo_root / "scouting" / "candidates" / "gaia")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    text = render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
        bootstrap_iterations=2_000,
        bootstrap_seed=42,
    )
    return study, result, text


@pytest.fixture
def tau_bench_airline_tool_calling(repo_root: Path):
    from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
    from eval_audit.report.markdown import render_report
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze

    study = StudySpec.from_yaml(repo_root / "studies" / "tau-bench-airline-tool-calling.yaml")
    runs = HalTauBenchAdapter().load(repo_root / "scouting" / "candidates" / "tau-bench")
    result = analyze(study, runs, bootstrap_iterations=2_000, bootstrap_seed=42)
    text = render_report(
        result,
        study,
        runs,
        clock=lambda: FIXED_CLOCK,
        git_commit="snapshot",
        fixture_sha256="0" * 64,
        repo_root=repo_root,
        bootstrap_iterations=2_000,
        bootstrap_seed=42,
    )
    return study, result, text


def _extract_sensitivity_block(text: str, claim_id: str) -> str:
    """Return the sensitivity sub-block for the given claim id."""
    marker = f"**Verdict sensitivity** — `{claim_id}`"
    start = text.index(marker)
    # Block ends at the next heading-style marker (next ** or next ## section).
    rest = text[start:]
    # Look for the next blank line followed by another **... or a ## section.
    end_match = re.search(r"\n\n(?=(\*\*|## ))", rest)
    end = start + (end_match.start() if end_match else len(rest))
    return text[start:end]


def test_sensitivity__baseline_row_matches_claims_table_verdict(gaia_hal_generalist) -> None:
    """WHEN the renderer emits the sensitivity sub-block for any claim,
    THEN the table's first row reads `| baseline | locked | <verdict> |` where
    <verdict> is exactly the same decision_impact value the Claims table reports.
    """
    _study, result, text = gaia_hal_generalist

    for claim in result.claims:
        block = _extract_sensitivity_block(text, claim.claim_id)
        # Pull the baseline row.
        baseline_match = re.search(r"\| baseline \| locked \| (\S+) \|", block)
        assert baseline_match, f"baseline row missing for {claim.claim_id}"
        baseline_verdict = baseline_match.group(1)

        # Pull the verdict from the Claims table for the same claim.
        # Claims table rows look like: | <claim_id> | declared_reanalysis | ... | <verdict> |
        claims_table_match = re.search(
            rf"\| {re.escape(claim.claim_id)} \|.*?\|\s*(\S+)\s*\|\s*$",
            text,
            flags=re.MULTILINE,
        )
        assert claims_table_match, f"claims table row missing for {claim.claim_id}"
        claims_verdict = claims_table_match.group(1)

        assert baseline_verdict == claims_verdict, (
            f"baseline {baseline_verdict!r} != claims-table {claims_verdict!r} "
            f"for {claim.claim_id}"
        )


def test_sensitivity__six_perturbation_rows_present_and_ordered(tau_bench_airline_tool_calling) -> None:
    """WHEN the renderer emits the sensitivity sub-block,
    THEN the rows after the baseline appear in the locked order.
    """
    _study, result, text = tau_bench_airline_tool_calling

    expected_rows = [
        ("alpha", "0.01"),
        ("alpha", "0.10"),
        ("errored_policy", "excluded"),
        ("correction_method", "none"),
        ("cost_gap_threshold", "0.05"),
        ("cost_gap_threshold", "0.20"),
    ]

    for claim in result.claims:
        block = _extract_sensitivity_block(text, claim.claim_id)
        # Extract every | dim | value | verdict | row in order.
        rows = re.findall(r"\| (\S+) \| (\S+) \| ([^|]+) \|", block)
        # First row should be the header `dimension | value | verdict`, second the
        # separator, third the baseline. Skip header + separator.
        data_rows = [(d, v) for d, v, _ in rows if d != "dimension" and not d.startswith("---")]
        assert data_rows[0] == ("baseline", "locked")
        assert data_rows[1:] == expected_rows, (
            f"sensitivity rows out of order for {claim.claim_id}: {data_rows[1:]}"
        )


def test_sensitivity__verdicts_are_in_controlled_vocabulary(tau_bench_airline_tool_calling) -> None:
    """Every perturbation row's verdict is one of the six controlled-vocabulary
    values, optionally followed by ` ← flips`.
    """
    from eval_audit.report.decisions import DECISION_IMPACT_VOCAB

    _study, result, text = tau_bench_airline_tool_calling

    for claim in result.claims:
        block = _extract_sensitivity_block(text, claim.claim_id)
        rows = re.findall(r"\| (\S+) \| (\S+) \| ([^|]+) \|", block)
        for d, v, verdict_cell in rows:
            if d == "dimension" or d.startswith("---"):
                continue
            cell = verdict_cell.strip()
            cell_no_flip = cell.replace(" ← flips", "")
            assert cell_no_flip in DECISION_IMPACT_VOCAB, (
                f"verdict {cell_no_flip!r} not in controlled vocabulary "
                f"(claim={claim.claim_id}, dim={d}, value={v})"
            )


def test_sensitivity__flip_annotation_only_on_non_baseline_verdicts(tau_bench_airline_tool_calling) -> None:
    """A row's verdict cell ends with ` ← flips` iff the verdict differs from
    the baseline verdict for the same claim.
    """
    _study, result, text = tau_bench_airline_tool_calling

    for claim in result.claims:
        block = _extract_sensitivity_block(text, claim.claim_id)
        rows = re.findall(r"\| (\S+) \| (\S+) \| ([^|]+) \|", block)
        # Locate baseline.
        baseline_verdict = None
        for d, _v, verdict_cell in rows:
            if d == "baseline":
                baseline_verdict = verdict_cell.strip()
                break
        assert baseline_verdict is not None

        for d, v, verdict_cell in rows:
            if d == "dimension" or d.startswith("---") or d == "baseline":
                continue
            cell = verdict_cell.strip()
            has_flip = "← flips" in cell
            verdict_only = cell.replace(" ← flips", "")
            differs_from_baseline = verdict_only != baseline_verdict
            assert has_flip == differs_from_baseline, (
                f"flip annotation mismatch (claim={claim.claim_id}, dim={d}, "
                f"value={v}): cell={cell!r}, baseline={baseline_verdict!r}"
            )


def test_sensitivity__nine_section_shape_unchanged(tau_bench_airline_tool_calling) -> None:
    """The sub-block does NOT break the nine-section shape contract."""
    _study, _result, text = tau_bench_airline_tool_calling

    headings = [line for line in text.splitlines() if line.startswith("## ")]
    section_titles = [h.removeprefix("## ").strip() for h in headings]
    assert section_titles == [
        "Audit Summary",
        "Study",
        "Provenance",
        "Per-agent summary",
        "Claims",
        "Robustness Review",
        "Cost-quality view",
        "Residual risks",
        "Reproducibility footer",
    ]

    # Sensitivity sub-blocks live entirely between the Claims table and the
    # Robustness Review heading.
    claims_idx = text.index("## Claims")
    rr_idx = text.index("## Robustness Review")
    block = text[claims_idx:rr_idx]
    assert "**Verdict sensitivity**" in block
    # And NOT outside that range.
    assert "**Verdict sensitivity**" not in text[:claims_idx]
    assert "**Verdict sensitivity**" not in text[rr_idx:]


def test_sensitivity__multiple_claims_one_subblock_each(tau_bench_airline_tool_calling) -> None:
    """A study with multiple claims emits one sub-block per claim, in
    claim-row order.
    """
    _study, result, text = tau_bench_airline_tool_calling

    claim_ids = [c.claim_id for c in result.claims]
    indices = [text.index(f"**Verdict sensitivity** — `{cid}`") for cid in claim_ids]
    assert indices == sorted(indices), (
        "sensitivity sub-blocks not in claim-row order"
    )
    # Three sub-blocks total (one per claim).
    assert text.count("**Verdict sensitivity**") == len(claim_ids)
