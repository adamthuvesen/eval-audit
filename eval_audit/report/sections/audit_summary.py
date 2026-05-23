"""Audit summary section rendering."""

from __future__ import annotations

import polars as pl

from eval_audit.report import ReportContractError
from eval_audit.report.decisions import decision_impact
from eval_audit.report.presentation import StudyPresentation
from eval_audit.report.sensitivity import claim_context_for_result
from eval_audit.report.summary import claim_status, paired_task_count
from eval_audit.report.vocabulary import VERDICT_RATIONALE
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats.results import AnalysisResult


def what_would_change_it(
    target_mde: float | None,
    ci_half_width: float,
    n_paired: int,
) -> str:
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


def count_residual_risks(residual_risks_text: str) -> int:
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


def reviewer_pushback(
    per_agent: list,
    presentation: StudyPresentation,
) -> str:
    caveats: list[str] = []
    total_errored = sum(s.n_errored for s in per_agent)
    if total_errored > 0:
        n_agents = sum(1 for s in per_agent if s.n_errored > 0)
        agents_word = "agent" if n_agents == 1 else "agents"
        caveats.append(
            f"errored rows present ({total_errored} across {n_agents} {agents_word})"
        )
    if presentation.cost_provenance == CostProvenance.AS_REPORTED_ONLY.value:
        caveats.append("cost provenance is as_reported_only")
    elif presentation.cost_provenance == CostProvenance.COST_NOT_AVAILABLE.value:
        caveats.append("cost provenance is cost_not_available")
    risks_count = count_residual_risks(presentation.residual_risks_text)
    if risks_count > 0:
        plural = "s" if risks_count != 1 else ""
        caveats.append(f"{risks_count} residual risk{plural} inherited from scouting")
    if not caveats:
        return "none flagged at this stage"
    return ", ".join(caveats)


def render_audit_summary_stanza(
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
    if decision_token not in VERDICT_RATIONALE:
        raise ReportContractError(
            f"decision_impact={decision_token!r} has no verdict rationale; "
            f"expected one of {sorted(VERDICT_RATIONALE)}"
        )
    rationale = VERDICT_RATIONALE[decision_token]
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
        f"- **What would change it:** {what_would_change_it(target_mde, ci_half_width, n_paired)}",
        f"- **Reviewer pushback:** {pushback}",
    ]


def render_audit_summary(
    result: AnalysisResult,
    study: StudySpec,
    runs: pl.DataFrame,
    presentation: StudyPresentation,
) -> list[str]:
    parts: list[str] = ["## Audit Summary\n"]
    target_mde = study.inference.target_mde
    pushback = reviewer_pushback(result.per_agent, presentation)
    multi_claim = len(result.claims) > 1
    for c in result.claims:
        ctx = claim_context_for_result(c, result, study)
        di = decision_impact(ctx)
        status = claim_status(c.rejects_null, ctx.direction_matches_claim)
        ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0
        n_paired = paired_task_count(runs, c.treatment, c.control)
        if multi_claim:
            parts.append(f"### Claim `{c.claim_id}`\n")
        parts.extend(
            render_audit_summary_stanza(
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
