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
    decision_impact,
    explain_decision_impact,
)
from eval_audit.report.sensitivity import claim_context_for_result, compute_sensitivity_rows
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.scouting_paths import resolve_decision_doc
from eval_audit.stats import AnalysisResult, analyze

_STATUS_VOCAB = {"supported", "unsupported", "inconclusive"}

# Each rationale follows the same template: which rule fired, what the rule
# means for the audit, and the action the verdict implies for a model selector.
# Per-claim numbers (delta, CI bounds, cost ratio) live in the **Why** bullet,
# not here.
_VERDICT_RATIONALE: dict[str, str] = {
    "switch": (
        "Treatment beat control significantly (the adjusted p-value rejects the null at "
        "the declared α) and in the direction the claim predicts. The data supports the "
        "claim. Action: switch the default selection to the treatment, subject to cost "
        "acceptance."
    ),
    "hold": (
        "Treatment differs from control significantly, but in the OPPOSITE direction of "
        "the claim. The data falsifies the claim's stated direction rather than confirming "
        "it. Action: hold the current selection; this evidence does not warrant a switch."
    ),
    "drop_from_shortlist": (
        "Treatment is Pareto-dominated on the cost-quality frontier — another agent "
        "achieves equal-or-better quality at equal-or-lower cost. No quality argument can "
        "rescue a dominated point. Action: drop the treatment from the shortlist before "
        "deciding among the rest."
    ),
    "rerun_more_n": (
        "The bootstrap CI for the delta crosses zero (no decisive direction), and the cost "
        "gap is below the material threshold of 10% of the cheaper arm. Neither side has a "
        "clean argument from this evidence. Action: collect more paired tasks before "
        "deciding; the current N is under-resolved for the question asked."
    ),
    "hedge_on_cost": (
        "The bootstrap CI for the delta crosses zero (no quality decision is available), "
        "but the cost gap is material (≥10% of the cheaper arm's cost). The decision "
        "pivots on cost preference rather than measured quality. Action: pick the cheaper "
        "arm unless the (statistically indistinguishable) quality difference matters to "
        "your use case."
    ),
    "inconclusive_no_action": (
        "The bootstrap CI for the delta is one-sided (does not cross zero), but the "
        "correction-adjusted p-value does not reject at α — the audit's declared "
        "inference contract requires a significant correction-adjusted test before "
        "claiming direction. No dominance or cost-gap rule fires. Action: keep the "
        "current selection until additional evidence (more N to tighten the test, or "
        "cost data that triggers the cost-gap rule) shifts the picture."
    ),
}


def _claim_status(rejects: bool, direction_matches: bool) -> str:
    if rejects and direction_matches:
        return "supported"
    if rejects and not direction_matches:
        return "unsupported"
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

    if cost_provenance_class == CostProvenance.AS_REPORTED_ONLY.value:
        caveats.append("cost provenance is as_reported_only")
    elif cost_provenance_class == CostProvenance.COST_NOT_AVAILABLE.value:
        caveats.append("cost provenance is cost_not_available")

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
    treatment_cost: float | None,
    control_cost: float | None,
    pushback: str,
) -> list[str]:
    """Emit the five bullet lines for one claim's audit-summary stanza."""
    if decision_token not in _VERDICT_RATIONALE:
        raise ReportContractError(
            f"decision_impact={decision_token!r} has no verdict rationale; "
            f"expected one of {sorted(_VERDICT_RATIONALE)}"
        )
    rationale = _VERDICT_RATIONALE[decision_token]

    delta_pp = claim.delta_point_estimate * 100
    ci_low_pp = claim.delta_ci_low * 100
    ci_high_pp = claim.delta_ci_high * 100
    if treatment_cost is None or control_cost is None:
        cost_str = "cost provenance is `cost_not_available`; no cost ratio is reported"
    elif control_cost > 0:
        cost_ratio = treatment_cost / control_cost
        cost_str = f"treatment is {cost_ratio:.2f}x the control's cost"
    else:
        cost_str = "control cost is zero so cost ratio is undefined"

    return [
        f"- **Verdict:** `{decision_token}` — {rationale}",
        f"- **Claim status:** {status}",
        (
            f"- **Why:** delta {delta_pp:+.2f} pp with bootstrap CI "
            f"[{ci_low_pp:+.2f} pp, {ci_high_pp:+.2f} pp] over {n_paired} paired tasks; "
            f"{cost_str}"
        ),
        f"- **What would change it:** {_what_would_change_it(target_mde, ci_half_width, n_paired)}",
        f"- **Reviewer pushback:** {pushback}",
    ]


def _copyable_claim_summary(
    *,
    claim_id: str,
    treatment: str,
    control: str,
    verdict: str,
    readiness: str,
    delta: float,
    ci_low: float,
    ci_high: float,
    cost_provenance_class: str,
    treatment_cost: float | None,
    control_cost: float | None,
) -> str:
    delta_pp = delta * 100
    ci_low_pp = ci_low * 100
    ci_high_pp = ci_high * 100
    if cost_provenance_class == CostProvenance.COST_NOT_AVAILABLE.value:
        caveat = (
            " Cost caveat: cost provenance is cost_not_available, so cost-derived "
            "views and cost-driven verdict branches are suppressed."
        )
    elif cost_provenance_class == CostProvenance.AS_REPORTED_ONLY.value:
        caveat = (
            " Cost caveat: cost provenance is as_reported_only, so costs come "
            "from reported totals rather than reconciled per-task reconstruction."
        )
    elif treatment_cost is None or control_cost is None:
        caveat = " Cost caveat: no reliable cost ratio is available."
    elif control_cost > 0:
        caveat = f" Cost note: treatment cost is {treatment_cost / control_cost:.2f}x control."
    else:
        caveat = " Cost note: control cost is zero, so the cost ratio is undefined."

    return (
        f"Claim `{claim_id}` verdict `{verdict}` for `{treatment}` vs `{control}`: "
        f"delta {delta_pp:+.2f} pp with bootstrap CI "
        f"[{ci_low_pp:+.2f} pp, {ci_high_pp:+.2f} pp]; "
        f"evidence readiness `{readiness}`.{caveat}"
    )


def _render_verdict_explainer(
    *,
    claim,
    cost_provenance_class: str,
    evidence_readiness: str,
    ctx,
) -> list[str]:
    explanation = explain_decision_impact(ctx)
    cost_gap_ratio = explanation.conditions["cost_gap_ratio"]
    cost_gap_text = "n/a" if cost_gap_ratio is None else f"{cost_gap_ratio:.2%}"
    suppressed = (
        ", ".join(explanation.suppressed_branches)
        if explanation.suppressed_branches
        else "none"
    )
    parts = [
        f"**Copyable summary** — `{claim.claim_id}`\n",
        _copyable_claim_summary(
            claim_id=claim.claim_id,
            treatment=claim.treatment,
            control=claim.control,
            verdict=explanation.verdict,
            readiness=evidence_readiness,
            delta=claim.delta_point_estimate,
            ci_low=claim.delta_ci_low,
            ci_high=claim.delta_ci_high,
            cost_provenance_class=cost_provenance_class,
            treatment_cost=ctx.treatment_cost_usd,
            control_cost=ctx.control_cost_usd,
        ),
        "",
        f"**Verdict explainer** — `{claim.claim_id}`\n",
        f"- **First matching branch:** `{explanation.first_matching_branch}` → `{explanation.verdict}`",
        f"- **Rule path:** {explanation.summary}",
        (
            "- **Evaluated conditions:** "
            f"Pareto dominated={ctx.treatment_is_dominated}; "
            f"adjusted-p rejection={ctx.rejects_null}; "
            f"effect direction matches claim={ctx.direction_matches_claim}; "
            f"quality CI crosses zero={explanation.conditions['ci_crosses_zero']}; "
            f"cost gap ratio={cost_gap_text}; "
            f"material cost-gap threshold={explanation.conditions['cost_gap_threshold']:.0%}."
        ),
        f"- **Suppressed branches:** {suppressed}.",
        "",
    ]
    return parts


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


def _robustness_cost_threshold(
    rows, baseline: str, *, pareto_suppressed: bool = False
) -> tuple[str, str]:
    """Compose cost_gap_threshold={0.05,0.20} rows into one verdict."""
    if pareto_suppressed:
        # decision_impact's cost-gap branch is unreachable under suppression,
        # so cost_gap_threshold cannot pivot the verdict by construction.
        return (
            "n/a",
            "cost-gap threshold not applicable; cost provenance is "
            f"{CostProvenance.COST_NOT_AVAILABLE.value}",
        )
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
    if cost_provenance_class == CostProvenance.RECONCILED.value:
        return ("survives", "reconciled")
    if cost_provenance_class in (CostProvenance.AS_REPORTED_ONLY.value, "partial"):
        return ("caveat", cost_provenance_class)
    if cost_provenance_class == CostProvenance.COST_NOT_AVAILABLE.value:
        return (
            "does not survive",
            "cost_not_available — Pareto and cost-per-success suppressed; "
            "see Cost provenance caveat",
        )
    return ("does not survive", cost_provenance_class)


def _render_robustness_review_table(
    rows,
    baseline: str,
    target_mde: float | None,
    ci_half_width: float,
    cost_provenance_class: str,
    *,
    pareto_suppressed: bool = False,
) -> list[str]:
    """Emit the markdown table header + five fixed-order data rows."""
    parts = ["| Dimension | Result | Notes |", "|---|---|---|"]

    result, notes = _robustness_multiple_comparison(rows, baseline)
    parts.append(f"| Multiple-comparison correction | {result} | {notes} |")

    result, notes = _robustness_errored_policy(rows, baseline)
    parts.append(f"| Errored-row policy | {result} | {notes} |")

    result, notes = _robustness_cost_threshold(
        rows, baseline, pareto_suppressed=pareto_suppressed
    )
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
    pareto_suppressed = result.pareto_status == "suppressed_cost_not_available"

    for c in result.claims:
        rows = sensitivity_rows_by_claim[c.claim_id]
        baseline = rows[0].verdict
        ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0

        if multi_claim:
            parts.append(f"### Claim `{c.claim_id}`\n")

        parts.extend(
            _render_robustness_review_table(
                rows,
                baseline,
                target_mde,
                ci_half_width,
                cost_provenance_class,
                pareto_suppressed=pareto_suppressed,
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
    pushback = _reviewer_pushback(
        result.per_agent, cost_provenance_class, residual_risks_text
    )
    multi_claim = len(result.claims) > 1

    for c in result.claims:
        ctx = claim_context_for_result(c, result, study)
        di = decision_impact(ctx)
        status = _claim_status(c.rejects_null, ctx.direction_matches_claim)
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
                ctx.treatment_cost_usd,
                ctx.control_cost_usd,
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


def _render_per_agent_summary(result: AnalysisResult) -> list[str]:
    parts: list[str] = ["## Per-agent summary\n"]
    if result.pareto_status == "suppressed_cost_not_available":
        parts.append(
            "| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low "
            "| success_rate_ci_high |"
        )
        parts.append("|---|---:|---:|---:|---:|---:|")
        for s in result.per_agent:
            parts.append(
                f"| {s.agent_id} | {s.n_graded} | {s.n_errored} | "
                f"{_format_rate(s.success_rate)} | {_format_rate(s.success_rate_ci_low)} | "
                f"{_format_rate(s.success_rate_ci_high)} |"
            )
        parts.append("")
        parts.append(
            "_Cost columns suppressed: cost provenance is `cost_not_available`._"
        )
    else:
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
    return parts


def _render_cost_quality_view(result: AnalysisResult) -> list[str]:
    parts = ["## Cost-quality view\n"]
    if result.pareto_status == "suppressed_cost_not_available":
        parts.append(
            "_Cost-quality view suppressed: cost provenance is `cost_not_available`. "
            "See the **Cost provenance caveat** above._"
        )
        parts.append("")
        return parts

    pareto_sorted = sorted(result.pareto_frontier)
    parts.append(
        f"**Pareto frontier (max success_rate, min total_cost_usd):** {pareto_sorted}"
    )
    parts.append("")
    dominated = [
        s.agent_id for s in result.per_agent if s.agent_id not in result.pareto_frontier
    ]
    if dominated:
        parts.append(
            f"Dominated agents: {sorted(dominated)}. Each is dominated by another agent that "
            "achieves at least the same success_rate at no greater total_cost_usd."
        )
    else:
        parts.append("All agents are on the frontier; no dominance to report.")
    parts.append("")
    return parts


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


def _dominant_cost_provenance(runs: pl.DataFrame) -> str:
    """Most-frequent ``cost_provenance`` value in the runs frame.

    Used by controlled-evidence reports where there is no scouting
    cost-reconciliation.json — provenance is per-row in the canonical parquet.
    Falls back to ``n/a`` when the column is absent or empty.
    """
    if "cost_provenance" not in runs.columns or runs.is_empty():
        return "n/a"
    counts = runs.group_by("cost_provenance").len().sort("len", descending=True)
    if counts.is_empty():
        return "n/a"
    return str(counts.row(0)[0])


def _render_provenance_controlled_evidence(
    study: StudySpec,
    runs: pl.DataFrame,
    repo_root: Path,
    cost_provenance_class: str,
) -> list[str]:
    """Provenance block for controlled original-evidence exhibits.

    Surfaces the run-design artifact, task source, harness/scaffold version,
    model arms, run dates, rerun policy, and cost provenance class. Pulls
    its data from the runs frame's ``rerun_metadata`` column and the study
    spec — no scouting/candidates fixture is required.

    Spec source: ``controlled-evidence-exhibits``: "Controlled evidence
    reports identify original run provenance".
    """
    parts: list[str] = []

    run_plan_rel = f"scouting/{study.id}/run-plan.md"
    decision_rel = f"scouting/{study.id}-decision.md"
    run_plan_exists = (repo_root / run_plan_rel).exists()
    decision_exists = (repo_root / decision_rel).exists()

    parts.append(
        "- **mode:** `controlled_original_runs` — predeclared run, paired arms on "
        "the same task IDs under one harness; this is original evidence, not "
        "public-data reanalysis or a synthetic example."
    )
    if run_plan_exists:
        parts.append(f"- **run_plan:** `{run_plan_rel}`")
    if decision_exists:
        parts.append(f"- **decision_doc:** `{decision_rel}`")

    # Pull provenance from rerun_metadata. Use the first row to read fields
    # that are constant across rows (harness, harness_commit, task_source,
    # price_table_date) and aggregate where they vary (model_id, rerun count).
    if not runs.is_empty() and "rerun_metadata" in runs.columns:
        first_meta: dict = runs.row(0, named=True)["rerun_metadata"] or {}
        task_source = first_meta.get("task_source")
        harness_commit = first_meta.get("harness_commit")
        rerun_policy = first_meta.get("rerun_policy")
        price_table_date = first_meta.get("price_table_date")

        if task_source:
            parts.append(f"- **task_source:** `{task_source}`")
        harness_line = f"- **harness:** `{study.harness}`"
        if harness_commit and harness_commit != "unknown":
            harness_line += f" at git commit `{harness_commit}`"
        parts.append(harness_line)

        # Model arms with their concrete model_ids and run counts.
        arm_summary = (
            runs.group_by(["agent_id", "model_id"])
            .agg(pl.col("run_id").n_unique().alias("n_runs"))
            .sort("agent_id")
        )
        parts.append("- **model_arms:**")
        for row in arm_summary.iter_rows(named=True):
            parts.append(
                f"  - `{row['agent_id']}` → `{row['model_id']}` "
                f"({row['n_runs']} run(s) per task)"
            )

        if rerun_policy:
            parts.append(f"- **rerun_policy:** `{rerun_policy}`")

        # Run date range from the timestamp column.
        if "timestamp" in runs.columns:
            with_ts = runs.filter(pl.col("timestamp").is_not_null())
            if not with_ts.is_empty():
                ts_min = with_ts["timestamp"].min()
                ts_max = with_ts["timestamp"].max()
                if ts_min == ts_max:
                    parts.append(f"- **run_dates:** `{ts_min.date().isoformat()}` (UTC)")
                else:
                    parts.append(
                        f"- **run_dates:** `{ts_min.date().isoformat()}` to "
                        f"`{ts_max.date().isoformat()}` (UTC)"
                    )

        if price_table_date:
            parts.append(f"- **price_table_pinned_at:** `{price_table_date}`")
    else:
        parts.append(f"- **harness:** `{study.harness}`")

    # Cost provenance class with row-level coverage when known.
    if "cost_provenance" in runs.columns and not runs.is_empty():
        total = runs.height
        match = runs.filter(pl.col("cost_provenance") == cost_provenance_class).height
        parts.append(
            f"- **cost_provenance:** `{cost_provenance_class}` ({match}/{total} rows)"
        )
    else:
        parts.append(f"- **cost_provenance:** `{cost_provenance_class}`")

    parts.append("")
    return parts


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
    evidence_readiness: str = "ready",
    check_sha256: str = "0" * 64,
) -> str:
    """Render a deterministic markdown report for one declared-claim reanalysis.

    `runs` is required so the verdict-sensitivity sub-block can recompute the
    errored-row-excluded perturbation against the original frame. Bootstrap
    parameters are passed through so the perturbed bootstrap matches the
    baseline's iteration count and seed.
    """
    _validate_report_outcome(study)
    decision_md, decision_md_label = resolve_decision_doc(
        repo_root, study.benchmark, study.id
    )
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
    elif study.analysis_mode == "preregistered":
        # Controlled-evidence path: cost provenance is per-row in the runs frame.
        cost_provenance_class = _dominant_cost_provenance(runs)
    else:
        # Public-submission re-analyses (declared_reanalysis) without a scouting
        # cost-reconciliation.json file. Today this fires for cost-suppressed
        # studies where the upstream artifacts expose no cost and provenance is
        # carried row-by-row as `cost_not_available`. Other provenance classes
        # for declared_reanalysis still come from the cost-reconciliation.json
        # so existing exhibits stay byte-identical.
        row_level = _dominant_cost_provenance(runs)
        if row_level == CostProvenance.COST_NOT_AVAILABLE.value:
            cost_provenance_class = row_level
    source_url = ""
    retrieved_at = ""
    source_fixture_rel = f"scouting/candidates/{benchmark_dir}/sample.parquet"
    if provenance.exists():
        prov = json.loads(provenance.read_text())
        source_url = prov.get("source_url", "")
        retrieved_at = prov.get("retrieved_at", "")
    else:
        # Public-submission re-analyses without a scouting/candidates package
        # commit their fixture under examples/<study.id>/ instead. Pick that up
        # so the Provenance section points at real artifacts, not stale paths.
        examples_provenance = repo_root / "examples" / study.id / "provenance.json"
        if examples_provenance.exists():
            prov = json.loads(examples_provenance.read_text())
            source_fixture_rel = f"examples/{study.id}/runs.parquet"
            sources = prov.get("sources") or []
            if sources:
                source_url = sources[0].get("url", "")
            retrieved_at = prov.get("fetched_at_utc", "")
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
    if study.analysis_mode == "preregistered":
        parts.extend(
            _render_provenance_controlled_evidence(
                study, runs, repo_root, cost_provenance_class
            )
        )
    else:
        parts.append(f"- **source_fixture:** `{source_fixture_rel}`")
        parts.append(f"- **source_url:** {source_url}")
        parts.append(f"- **retrieved_at:** `{retrieved_at}`")
        parts.append(f"- **price_table_pinned_at:** `{PRICE_TABLE_PINNED_AT}`")
        parts.append(f"- **cost_provenance:** `{cost_provenance_class}`")
        parts.append("")

    if cost_provenance_class == CostProvenance.AS_REPORTED_ONLY.value:
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

    if cost_provenance_class == CostProvenance.COST_NOT_AVAILABLE.value:
        parts.append("### Cost provenance caveat\n")
        parts.append("> ⚠️ Cost provenance: cost_not_available")
        parts.append("")
        parts.append(
            "The upstream artifacts for this study do not expose complete, stable "
            "cost fields. Per-task cost cannot be reconstructed with the report's "
            "pinned price policy, and no complete per-run reported total is available. "
            "Rather than smuggle in zeros, this report **suppresses** every "
            "cost-derived view: per-agent `total_cost_usd` and `cost_per_success_usd` "
            "columns are omitted from the Per-agent summary, the Cost-quality view "
            "(Pareto frontier) is suppressed, and `decision_impact` cannot return "
            "`hedge_on_cost` for any claim in this study."
        )
        parts.append("")
        suppressed_agents = [s.agent_id for s in result.per_agent if s.total_cost_usd is None]
        if suppressed_agents:
            parts.append("**Cost-suppressed agents:**\n")
            for agent_id in suppressed_agents:
                parts.append(f"- `{agent_id}`")
            parts.append("")
        parts.append(
            "Cost-related residual risks are inherited from the scouting decision "
            "document (see Residual risks below)."
        )
        parts.append("")

    # 4. Per-agent summary
    parts.extend(_render_per_agent_summary(result))

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
    mde_per_claim: list[tuple[str, float, float]] = []  # (claim_id, ci_half_width, target_mde)
    for c in result.claims:
        ctx = claim_context_for_result(c, result, study)
        di = decision_impact(ctx)
        status = _claim_status(c.rejects_null, ctx.direction_matches_claim)
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

    for c in result.claims:
        ctx = claim_context_for_result(c, result, study)
        parts.extend(
            _render_verdict_explainer(
                claim=c,
                cost_provenance_class=cost_provenance_class,
                evidence_readiness=evidence_readiness,
                ctx=ctx,
            )
        )

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
    pareto_suppressed_sens = result.pareto_status == "suppressed_cost_not_available"
    for c in result.claims:
        rows = sensitivity_rows_by_claim[c.claim_id]
        baseline_verdict = rows[0].verdict
        parts.append(f"**Verdict sensitivity** — `{c.claim_id}`\n")
        parts.append("| dimension | value | verdict |")
        parts.append("|---|---|---|")
        for r in rows:
            # Under cost suppression the cost-gap branch in decision_impact is
            # unreachable; rendering numeric verdicts on cost_gap_threshold
            # perturbations would falsely imply the threshold pivots the
            # verdict. Mark them N/A so the suppression is visible in the very
            # table designed to expose it.
            if pareto_suppressed_sens and r.dimension == "cost_gap_threshold":
                verdict_cell = "n/a (cost suppressed)"
            else:
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
    parts.extend(_render_cost_quality_view(result))

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
    parts.append(f"- **evidence_readiness:** `{evidence_readiness}`")
    parts.append(f"- **check_sha256:** `{check_sha256}`")
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
    evidence_readiness: str = "ready",
    check_sha256: str = "0" * 64,
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
        evidence_readiness=evidence_readiness,
        check_sha256=check_sha256,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return out_path
