"""Deterministic markdown report renderer for declared-claim reanalyses."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import polars as pl

from eval_audit.fixtures import benchmark_dir_name
from eval_audit.ingest._prices import PRICE_TABLE_PINNED_AT
from eval_audit.report import ReportContractError
from eval_audit.report.decisions import (
    DECISION_IMPACT_VOCAB,
    ClaimContext,
    decision_impact,
    direction_matches_claim,
)
from eval_audit.schema import StudySpec
from eval_audit.stats import AnalysisResult, analyze

_STATUS_VOCAB = {"supported", "unsupported", "inconclusive"}

_VERDICT_GLOSS: dict[str, str] = {
    "switch": "claim is supported and the effect favours the treatment",
    "hold": "rejection is in the wrong direction; treatment fails the claim",
    "drop_from_shortlist": "treatment is Pareto-dominated on cost-quality",
    "rerun_more_n": "CI crosses zero with no material cost gap; needs more data",
    "hedge_on_cost": "CI crosses zero and the cost gap is material",
    "inconclusive_no_action": "result does not meet any decision threshold",
}


def _claim_status(rejects: bool, direction_matches: bool, ci_crosses_zero: bool) -> str:
    if rejects and direction_matches:
        return "supported"
    if rejects and not direction_matches:
        return "unsupported"
    if ci_crosses_zero:
        return "inconclusive"
    return "inconclusive"


def _what_would_change_it(
    target_mde: float | None,
    ci_half_width: float,
    n_paired: int,
) -> str:
    """Render the audit summary's resolution-planning line.

    When target_mde is declared, the line carries a concrete N estimate
    derived from the variance-fixed scaling approximation in
    ``eval_audit/stats/resolution.py``. The approximation is named explicitly
    in the rendered output so readers see the model used.
    """
    if target_mde is None:
        return (
            "declaring an inference.target_mde would let this report estimate "
            "required sample size"
        )
    from eval_audit.stats.resolution import estimate_required_paired_tasks

    if ci_half_width > target_mde:
        est = estimate_required_paired_tasks(n_paired, ci_half_width, target_mde)
        return (
            f"~{est.additional_tasks} more paired tasks would tighten the CI to "
            f"≤ MDE (estimated, variance-fixed scaling)"
        )
    return (
        f"the study already resolves below the declared MDE "
        f"(CI half-width {ci_half_width * 100:.2f} pp ≤ MDE "
        f"{target_mde * 100:.2f} pp); no additional N would change the verdict"
    )


def _count_residual_risks(residual_risks_text: str) -> int:
    """Count numbered list items in an extracted residual-risks block.

    Returns 0 when the block is the placeholder for a missing scouting decision
    document or signals that no risks were found.
    """
    if "no scouting decision document at" in residual_risks_text:
        return 0
    if "no residual risks found" in residual_risks_text:
        return 0
    count = 0
    for line in residual_risks_text.splitlines():
        stripped = line.strip()
        if len(stripped) >= 2 and stripped[0].isdigit() and stripped[1] == ".":
            count += 1
    return count


def _reviewer_pushback(
    per_agent: list,
    cost_provenance_class: str,
    residual_risks_text: str,
) -> str:
    """Comma-join existing caveats in fixed order, or signal none flagged."""
    caveats: list[str] = []

    total_errored = sum(s.n_errored for s in per_agent)
    if total_errored > 0:
        n_agents = sum(1 for s in per_agent if s.n_errored > 0)
        agents_word = "agent" if n_agents == 1 else "agents"
        caveats.append(
            f"errored rows present ({total_errored} across {n_agents} {agents_word})"
        )

    if cost_provenance_class == "as_reported_only":
        caveats.append("cost provenance is as_reported_only")

    risks_count = _count_residual_risks(residual_risks_text)
    if risks_count > 0:
        plural = "s" if risks_count != 1 else ""
        caveats.append(f"{risks_count} residual risk{plural} inherited from scouting")

    if not caveats:
        return "none flagged at this stage"
    return ", ".join(caveats)


def _render_audit_summary_stanza(
    claim,
    decision_token: str,
    status: str,
    target_mde: float | None,
    ci_half_width: float,
    n_paired: int,
    treatment_cost: float,
    control_cost: float,
    pushback: str,
) -> list[str]:
    """Emit the five bullet lines for one claim's audit-summary stanza."""
    if decision_token not in _VERDICT_GLOSS:
        raise ReportContractError(
            f"decision_impact={decision_token!r} has no verdict gloss; "
            f"expected one of {sorted(_VERDICT_GLOSS)}"
        )
    gloss = _VERDICT_GLOSS[decision_token]

    delta_pp = claim.delta_point_estimate * 100
    ci_low_pp = claim.delta_ci_low * 100
    ci_high_pp = claim.delta_ci_high * 100
    if control_cost > 0:
        cost_ratio = treatment_cost / control_cost
        cost_str = f"treatment is {cost_ratio:.2f}x the control's cost"
    else:
        cost_str = "control cost is zero so cost ratio is undefined"

    return [
        f"- **Verdict:** `{decision_token}` — {gloss}",
        f"- **Claim status:** {status}",
        (
            f"- **Why:** delta {delta_pp:+.2f} pp with bootstrap CI "
            f"[{ci_low_pp:+.2f} pp, {ci_high_pp:+.2f} pp] over {n_paired} paired tasks; "
            f"{cost_str}"
        ),
        f"- **What would change it:** {_what_would_change_it(target_mde, ci_half_width, n_paired)}",
        f"- **Reviewer pushback:** {pushback}",
    ]


_ROBUSTNESS_DIMENSIONS: tuple[str, ...] = (
    "Multiple-comparison correction",
    "Errored-row policy",
    "Cost-threshold sensitivity",
    "Target MDE",
    "Cost provenance",
)


def _robustness_multiple_comparison(rows, baseline: str) -> tuple[str, str]:
    """Compose alpha={0.01,0.10} + correction_method=none rows into one verdict."""
    flipped: list[str] = []
    for r in rows:
        if r.dimension == "alpha" and r.value == "0.01" and r.verdict != baseline:
            flipped.append("α=0.01")
        elif r.dimension == "alpha" and r.value == "0.10" and r.verdict != baseline:
            flipped.append("α=0.10")
        elif (
            r.dimension == "correction_method"
            and r.value == "none"
            and r.verdict != baseline
        ):
            flipped.append("correction=none")
    if not flipped:
        return (
            "survives",
            "verdict unchanged at α∈{0.01, 0.10} and with correction=none",
        )
    return ("does not survive", f"verdict flips at {', '.join(flipped)}")


def _robustness_errored_policy(rows, baseline: str) -> tuple[str, str]:
    """Compose the errored_policy=excluded row into one verdict."""
    for r in rows:
        if r.dimension == "errored_policy" and r.value == "excluded":
            if r.verdict == baseline:
                return ("survives", "verdict unchanged when errored rows excluded")
            return (
                "does not survive",
                f"verdict flips when errored rows excluded ({baseline} → {r.verdict})",
            )
    raise ReportContractError(
        "errored_policy=excluded row missing from sensitivity rows"
    )


def _robustness_cost_threshold(rows, baseline: str) -> tuple[str, str]:
    """Compose cost_gap_threshold={0.05,0.20} rows into one verdict."""
    flipped: list[str] = []
    for r in rows:
        if r.dimension == "cost_gap_threshold" and r.verdict != baseline:
            flipped.append(r.value)
    if not flipped:
        return (
            "survives",
            "verdict unchanged at cost_gap_threshold∈{0.05, 0.20}",
        )
    return (
        "does not survive",
        f"verdict flips at cost_gap_threshold={', '.join(flipped)}",
    )


def _robustness_target_mde(
    target_mde: float | None, ci_half_width: float
) -> tuple[str, str]:
    """Compose CI-half-width-vs-target_mde into one verdict."""
    if target_mde is None:
        return ("not assessed", "inference.target_mde not declared")
    half_pp = ci_half_width * 100
    mde_pp = target_mde * 100
    if ci_half_width <= target_mde:
        return (
            "survives",
            f"CI half-width {half_pp:.2f} pp ≤ MDE {mde_pp:.2f} pp; sufficiently resolved",
        )
    return (
        "does not survive",
        f"CI half-width {half_pp:.2f} pp > MDE {mde_pp:.2f} pp; under-resolved",
    )


def _robustness_cost_provenance(cost_provenance_class: str) -> tuple[str, str]:
    """Map cost-reconciliation outcome to the four-value Result vocabulary."""
    if cost_provenance_class == "reconciled":
        return ("survives", "reconciled")
    if cost_provenance_class in ("as_reported_only", "partial"):
        return ("caveat", cost_provenance_class)
    return ("does not survive", cost_provenance_class)


def _render_robustness_review_table(
    rows,
    baseline: str,
    target_mde: float | None,
    ci_half_width: float,
    cost_provenance_class: str,
) -> list[str]:
    """Emit the markdown table header + five fixed-order data rows."""
    parts = ["| Dimension | Result | Notes |", "|---|---|---|"]

    result, notes = _robustness_multiple_comparison(rows, baseline)
    parts.append(f"| Multiple-comparison correction | {result} | {notes} |")

    result, notes = _robustness_errored_policy(rows, baseline)
    parts.append(f"| Errored-row policy | {result} | {notes} |")

    result, notes = _robustness_cost_threshold(rows, baseline)
    parts.append(f"| Cost-threshold sensitivity | {result} | {notes} |")

    result, notes = _robustness_target_mde(target_mde, ci_half_width)
    parts.append(f"| Target MDE | {result} | {notes} |")

    result, notes = _robustness_cost_provenance(cost_provenance_class)
    parts.append(f"| Cost provenance | {result} | {notes} |")

    return parts


def _render_robustness_review(
    result,
    study: StudySpec,
    sensitivity_rows_by_claim: dict,
    cost_provenance_class: str,
) -> list[str]:
    """Emit the `## Robustness Review` section.

    Single-claim studies emit a flat table; multi-claim studies emit one
    `### Claim <id>` sub-stanza per claim, in claim-table order. Composes
    sensitivity rows (already computed for the Verdict sensitivity sub-block)
    + MDE context + cost-provenance class — no new computation.
    """
    parts: list[str] = ["## Robustness Review\n"]

    target_mde = study.inference.target_mde
    multi_claim = len(result.claims) > 1

    for c in result.claims:
        rows = sensitivity_rows_by_claim[c.claim_id]
        baseline = rows[0].verdict
        ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0

        if multi_claim:
            parts.append(f"### Claim `{c.claim_id}`\n")

        parts.extend(
            _render_robustness_review_table(
                rows, baseline, target_mde, ci_half_width, cost_provenance_class
            )
        )
        parts.append("")

    return parts


def _render_audit_summary(
    result,
    study: StudySpec,
    runs: pl.DataFrame,
    cost_provenance_class: str,
    residual_risks_text: str,
) -> list[str]:
    """Emit the `## Audit Summary` section for the report.

    Single-claim studies emit a flat five-bullet stanza. Multi-claim studies
    emit one `### Claim <claim_id>` sub-stanza per claim, in claim-table
    order. The Reviewer pushback line is study-level and identical across
    all stanzas.
    """
    parts: list[str] = []
    parts.append("## Audit Summary\n")

    target_mde = study.inference.target_mde
    by_id = {s.agent_id: s for s in result.per_agent}
    pushback = _reviewer_pushback(
        result.per_agent, cost_provenance_class, residual_risks_text
    )
    multi_claim = len(result.claims) > 1

    for c in result.claims:
        ci_crosses = c.delta_ci_low <= 0.0 <= c.delta_ci_high
        direction_matches = direction_matches_claim(
            study.primary_outcome.direction, c.delta_point_estimate
        )
        ctx = ClaimContext(
            rejects_null=c.rejects_null,
            delta_point_estimate=c.delta_point_estimate,
            delta_ci_low=c.delta_ci_low,
            delta_ci_high=c.delta_ci_high,
            treatment_cost_usd=by_id[c.treatment].total_cost_usd,
            control_cost_usd=by_id[c.control].total_cost_usd,
            treatment_is_dominated=c.treatment not in result.pareto_frontier,
            direction_matches_claim=direction_matches,
        )
        di = decision_impact(ctx)
        status = _claim_status(c.rejects_null, direction_matches, ci_crosses)
        ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0
        n_paired = _paired_task_count(runs, c.treatment, c.control)

        if multi_claim:
            parts.append(f"### Claim `{c.claim_id}`\n")

        parts.extend(
            _render_audit_summary_stanza(
                c,
                di,
                status,
                target_mde,
                ci_half_width,
                n_paired,
                by_id[c.treatment].total_cost_usd,
                by_id[c.control].total_cost_usd,
                pushback,
            )
        )
        parts.append("")

    return parts


def _paired_task_count(runs: pl.DataFrame, treatment: str, control: str) -> int:
    """Count the task IDs shared by both claim arms."""
    treatment_tasks = (
        runs.filter(pl.col("agent_id") == treatment)
        .select("task_id")
        .unique()
    )
    control_tasks = (
        runs.filter(pl.col("agent_id") == control)
        .select("task_id")
        .unique()
    )
    return treatment_tasks.join(control_tasks, on="task_id", how="inner").height


def _format_pp(delta: float) -> str:
    return f"{delta * 100:+.2f} pp"


def _format_currency(value: float) -> str:
    return f"${value:.2f}"


def _format_rate(value: float) -> str:
    return f"{value:.4f}"


def _validate_report_outcome(study: StudySpec) -> None:
    if (
        study.primary_outcome.name != "success_rate"
        or study.primary_outcome.direction != "higher_is_better"
    ):
        raise ValueError(
            "v0 reports support only primary_outcome.name='success_rate' "
            "with direction='higher_is_better'"
        )
    for claim in study.claims:
        if claim.outcome != "success_rate":
            raise ValueError(
                f"v0 reports support only claim outcome 'success_rate' "
                f"(claim_id={claim.id!r}, outcome={claim.outcome!r})"
            )


# Aliases for the residual-risks decision-document path. The renderer resolves
# `scouting/<benchmark>-decision.md` by default; the aliases preserve Exhibit A's
# historical filename and translate `tau_bench` -> `tau-bench` to match the
# scouting fixture's hyphenated directory convention.
_DECISION_DOC_ALIAS = {
    "gaia": "exhibit-a-decision.md",
    "tau_bench": "tau-bench-decision.md",
}


def _resolve_decision_doc(repo_root: Path, benchmark: str) -> tuple[Path, str]:
    """Return (path, relative_label) for the per-benchmark scouting decision doc."""
    filename = _DECISION_DOC_ALIAS.get(benchmark, f"{benchmark}-decision.md")
    return repo_root / "scouting" / filename, f"scouting/{filename}"


def _extract_residual_risks(decision_md_path: Path, relative_label: str) -> str:
    """Extract the bulleted residual-risks list from the resolved scouting decision doc.

    Falls back to a single placeholder line when the file does not exist, so the
    Residual risks section preserves the seven-section shape contract.
    """
    if not decision_md_path.exists():
        return (
            f"_(no scouting decision document at {relative_label}; "
            "residual risks not surfaced.)_"
        )
    text = decision_md_path.read_text()
    start_match = re.search(r"^## Residual risks\s*$", text, flags=re.MULTILINE)
    if not start_match:
        return "(no residual risks found in scouting decision document)"
    start = start_match.end()
    end_match = re.search(r"^## ", text[start:], flags=re.MULTILINE)
    end = start + (end_match.start() if end_match else len(text) - start)
    block = text[start:end].strip()
    return block


def render_claim_row(row: dict) -> str:
    """Render a single claim row, validating its decision_impact value.

    Raises ReportContractError if the row's decision_impact is not in the controlled vocabulary.
    The target_mde column is included only when row['target_mde'] is set.
    """
    di = row.get("decision_impact")
    if di not in DECISION_IMPACT_VOCAB:
        raise ReportContractError(
            f"decision_impact={di!r} is not in controlled vocabulary {DECISION_IMPACT_VOCAB}"
        )
    status = row.get("status")
    if status not in _STATUS_VOCAB:
        raise ReportContractError(
            f"status={status!r} is not in controlled vocabulary {sorted(_STATUS_VOCAB)}"
        )
    if "target_mde" in row:
        return (
            f"| {row['claim_id']} | {row['mode']} | {row['status']} | "
            f"{row['effect']} | {row['target_mde']} | "
            f"{row['adjusted_result']} | {row['decision_impact']} |"
        )
    return (
        f"| {row['claim_id']} | {row['mode']} | {row['status']} | "
        f"{row['effect']} | {row['adjusted_result']} | {row['decision_impact']} |"
    )


def render_report(
    result: AnalysisResult,
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    clock: Callable[[], datetime],
    git_commit: str,
    fixture_sha256: str,
    repo_root: Path,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
) -> str:
    """Render a deterministic markdown report for one declared-claim reanalysis.

    `runs` is required so the verdict-sensitivity sub-block can recompute the
    errored-row-excluded perturbation against the original frame. Bootstrap
    parameters are passed through so the perturbed bootstrap matches the
    baseline's iteration count and seed.
    """
    _validate_report_outcome(study)
    decision_md, decision_md_label = _resolve_decision_doc(repo_root, study.benchmark)
    benchmark_dir = benchmark_dir_name(study.benchmark)
    cost_recon = (
        repo_root
        / "scouting"
        / "candidates"
        / benchmark_dir
        / "cost-reconciliation.json"
    )
    provenance = (
        repo_root / "scouting" / "candidates" / benchmark_dir / "provenance.json"
    )

    # Pre-compute values used by the Audit Summary AND later sections so each
    # source file is read once.
    cost_provenance_class = "n/a"
    cost_recon_data: dict = {}
    if cost_recon.exists():
        cost_recon_data = json.loads(cost_recon.read_text())
        cost_provenance_class = cost_recon_data.get("outcome", "n/a")
    source_url = ""
    retrieved_at = ""
    if provenance.exists():
        prov = json.loads(provenance.read_text())
        source_url = prov.get("source_url", "")
        retrieved_at = prov.get("retrieved_at", "")
    residual_risks_text = _extract_residual_risks(decision_md, decision_md_label)

    rendered_at = clock().isoformat()

    parts: list[str] = []

    # 1. Audit Summary
    parts.extend(
        _render_audit_summary(
            result,
            study,
            runs,
            cost_provenance_class,
            residual_risks_text,
        )
    )

    # 2. Study
    parts.append("## Study\n")
    primary_claim = study.claims[0]
    parts.append(f"- **id:** `{study.id}`")
    parts.append(f"- **benchmark:** `{study.benchmark}`")
    parts.append(f"- **harness:** `{study.harness}`")
    parts.append(f"- **analysis_mode:** `{study.analysis_mode}`")
    parts.append(f"- **data_observation:** `{study.data_observation}`")
    parts.append(f"- **claim:** {primary_claim.text}")
    parts.append("")

    # 3. Provenance
    parts.append("## Provenance\n")
    parts.append(f"- **source_fixture:** `scouting/candidates/{benchmark_dir}/sample.parquet`")
    parts.append(f"- **source_url:** {source_url}")
    parts.append(f"- **retrieved_at:** `{retrieved_at}`")
    parts.append(f"- **price_table_pinned_at:** `{PRICE_TABLE_PINNED_AT}`")
    parts.append(f"- **cost_provenance:** `{cost_provenance_class}`")
    parts.append("")

    if cost_provenance_class == "as_reported_only":
        parts.append("### Cost provenance caveat\n")
        parts.append("> ⚠️ Cost provenance: as_reported_only")
        parts.append("")
        parts.append(
            "HAL's reported run-total cost is used directly because per-task cost "
            "reconstruction from token counts × pinned provider prices does not "
            "reconcile to HAL's reported total within the toolkit's 1% tolerance. "
            "Per-task cost analyses are therefore unavailable for this study; "
            "cost figures below are derived from the reported run-total divided by "
            "graded successes."
        )
        parts.append("")
        parts.append("**Divergences (per run):**\n")
        for d in cost_recon_data.get("divergences", []):
            agent_id = d.get("agent_id", "")
            reported = float(d.get("reported_cost_usd", 0.0))
            recon = float(d.get("reconstructed_cost_usd", 0.0))
            note = d.get("hypothesis", "")
            parts.append(
                f"- {agent_id} — reported ${reported:.2f}, reconstructed ${recon:.2f} "
                f"(note: {note})"
            )
        parts.append("")
        parts.append("**Caveats:**\n")
        for c in cost_recon_data.get("caveats", []):
            parts.append(f"- {c}")
        parts.append("")

    # 4. Per-agent summary
    parts.append("## Per-agent summary\n")
    parts.append(
        "| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low "
        "| success_rate_ci_high | total_cost_usd | cost_per_success_usd |"
    )
    parts.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in result.per_agent:
        cps = (
            "inf" if s.cost_per_success_usd == float("inf")
            else _format_currency(s.cost_per_success_usd)
        )
        parts.append(
            f"| {s.agent_id} | {s.n_graded} | {s.n_errored} | "
            f"{_format_rate(s.success_rate)} | {_format_rate(s.success_rate_ci_low)} | "
            f"{_format_rate(s.success_rate_ci_high)} | "
            f"{_format_currency(s.total_cost_usd)} | {cps} |"
        )
    parts.append("")

    # 5. Claims
    parts.append("## Claims\n")
    target_mde = study.inference.target_mde
    if target_mde is not None:
        parts.append(
            "| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |"
        )
        parts.append("|---|---|---|---|---|---|---|")
    else:
        parts.append("| claim_id | mode | status | effect | adjusted_result | decision_impact |")
        parts.append("|---|---|---|---|---|---|")
    by_id = {s.agent_id: s for s in result.per_agent}
    mde_per_claim: list[tuple[str, float, float]] = []  # (claim_id, ci_half_width, target_mde)
    for c in result.claims:
        ci_crosses = c.delta_ci_low <= 0.0 <= c.delta_ci_high
        direction_matches = direction_matches_claim(
            study.primary_outcome.direction,
            c.delta_point_estimate,
        )
        ctx = ClaimContext(
            rejects_null=c.rejects_null,
            delta_point_estimate=c.delta_point_estimate,
            delta_ci_low=c.delta_ci_low,
            delta_ci_high=c.delta_ci_high,
            treatment_cost_usd=by_id[c.treatment].total_cost_usd,
            control_cost_usd=by_id[c.control].total_cost_usd,
            treatment_is_dominated=c.treatment not in result.pareto_frontier,
            direction_matches_claim=direction_matches,
        )
        di = decision_impact(ctx)
        status = _claim_status(c.rejects_null, direction_matches, ci_crosses)
        adj = "n/a" if c.adjusted_p_value is None else f"{c.adjusted_p_value:.4f}"
        row = {
            "claim_id": c.claim_id,
            "mode": study.analysis_mode,
            "status": status,
            "effect": _format_pp(c.delta_point_estimate),
            "adjusted_result": adj,
            "decision_impact": di,
        }
        if target_mde is not None:
            row["target_mde"] = _format_pp(target_mde)
            ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0
            mde_per_claim.append((c.claim_id, ci_half_width, target_mde))
        parts.append(render_claim_row(row))
    parts.append("")

    if target_mde is not None and mde_per_claim:
        parts.append("**MDE context**\n")
        for claim_id, half_width, mde in mde_per_claim:
            diff_pp = (half_width - mde) * 100
            if diff_pp < -0.5:
                wording = (
                    "the study has resolution finer than the declared MDE; "
                    "an effect of this size would be detectable"
                )
            elif abs(diff_pp) <= 0.5:
                wording = (
                    "the study sits at the declared MDE; "
                    "an effect of exactly this size sits on the detection boundary"
                )
            else:
                wording = (
                    "the study has resolution coarser than the declared MDE; "
                    "an effect at the declared MDE would not be reliably detected without more data"
                )
            parts.append(
                f"- `{claim_id}`: bootstrap CI half-width = {half_width * 100:.2f} pp "
                f"vs target_mde = {mde * 100:.2f} pp — {wording}."
            )
        parts.append("")

    # Precompute sensitivity rows once per claim. The errored_policy=excluded
    # perturbation re-bootstraps the graded-only frame, so this is the
    # expensive bit; the Verdict sensitivity sub-block and the Robustness
    # Review section both consume the same rows.
    from eval_audit.report.sensitivity import compute_sensitivity_rows

    sensitivity_rows_by_claim: dict[str, list] = {}
    for c in result.claims:
        sensitivity_rows_by_claim[c.claim_id] = compute_sensitivity_rows(
            c,
            runs,
            study,
            result,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        )

    # Verdict sensitivity sub-block (one per claim).
    for c in result.claims:
        rows = sensitivity_rows_by_claim[c.claim_id]
        baseline_verdict = rows[0].verdict
        parts.append(f"**Verdict sensitivity** — `{c.claim_id}`\n")
        parts.append("| dimension | value | verdict |")
        parts.append("|---|---|---|")
        for r in rows:
            verdict_cell = r.verdict
            if r.dimension != "baseline" and r.verdict != baseline_verdict:
                verdict_cell = f"{r.verdict} ← flips"
            parts.append(f"| {r.dimension} | {r.value} | {verdict_cell} |")
        parts.append("")

    # 6. Robustness Review
    parts.extend(
        _render_robustness_review(
            result, study, sensitivity_rows_by_claim, cost_provenance_class
        )
    )

    # 7. Cost-quality view
    parts.append("## Cost-quality view\n")
    pareto_sorted = sorted(result.pareto_frontier)
    parts.append(f"**Pareto frontier (max success_rate, min total_cost_usd):** {pareto_sorted}")
    parts.append("")
    dominated = [s.agent_id for s in result.per_agent if s.agent_id not in result.pareto_frontier]
    if dominated:
        parts.append(
            f"Dominated agents: {sorted(dominated)}. Each is dominated by another agent that "
            "achieves at least the same success_rate at no greater total_cost_usd."
        )
    else:
        parts.append("All agents are on the frontier; no dominance to report.")
    parts.append("")

    # 8. Residual risks
    parts.append("## Residual risks\n")
    parts.append(
        "**Inherited from scouting decision** (verbatim from "
        f"`{decision_md_label}`):\n"
    )
    parts.append(residual_risks_text)
    parts.append("")

    # 9. Reproducibility footer
    parts.append("## Reproducibility footer\n")
    parts.append(f"- **rendered_at:** `{rendered_at}`")
    parts.append(f"- **git_commit:** `{git_commit}`")
    parts.append(f"- **fixture_sha256:** `{fixture_sha256}`")
    parts.append(f"- **bootstrap_seed:** `{result.bootstrap_seed}`")
    parts.append("")

    return "\n".join(parts)


def render_report_to(
    out_path: Path,
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    clock: Callable[[], datetime],
    git_commit: str,
    fixture_sha256: str,
    repo_root: Path,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
) -> Path:
    """Run analyze() then render to disk. CrossHarnessComparisonError propagates
    BEFORE any file is written.
    """
    result = analyze(
        study,
        runs,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    text = render_report(
        result,
        study,
        runs,
        clock=clock,
        git_commit=git_commit,
        fixture_sha256=fixture_sha256,
        repo_root=repo_root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return out_path
