"""Deterministic markdown report renderer for declared-claim reanalyses."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import polars as pl

from eval_audit.report.caveats import (
    render_as_reported_only_caveat,
    render_cost_not_available_caveat,
)
from eval_audit.report.decisions import decision_impact
from eval_audit.report.formatters import format_pp
from eval_audit.report.presentation import StudyPresentation, resolve_study_presentation
from eval_audit.report.sections import audit_summary as audit_summary_section
from eval_audit.report.sections.audit_summary import (
    render_audit_summary,
    render_audit_summary_stanza,
    what_would_change_it,
)
from eval_audit.report.sections.claims_table import (
    copyable_claim_summary,
    render_claim_row,
    render_verdict_explainer,
)
from eval_audit.report.sections.per_agent import (
    render_cost_quality_view,
    render_per_agent_summary,
)
from eval_audit.report.sections.provenance_section import (
    render_provenance_controlled_evidence,
    render_public_provenance,
)
from eval_audit.report.sections.robustness import (
    ROBUSTNESS_DIMENSIONS,
    render_robustness_review,
    render_robustness_review_table,
    robustness_cost_provenance,
    robustness_cost_threshold,
    robustness_errored_policy,
    robustness_multiple_comparison,
    robustness_target_mde,
)
from eval_audit.report.sensitivity import claim_context_for_result, compute_sensitivity_rows
from eval_audit.report.summary import claim_status
from eval_audit.report.vocabulary import STATUS_VOCAB, VERDICT_RATIONALE
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats import AnalysisResult, analyze

# Test and snapshot stability: legacy private names re-exported from section modules.
_STATUS_VOCAB = STATUS_VOCAB
_VERDICT_RATIONALE = VERDICT_RATIONALE
_ROBUSTNESS_DIMENSIONS = ROBUSTNESS_DIMENSIONS
_what_would_change_it = what_would_change_it
_render_audit_summary_stanza = render_audit_summary_stanza


def _reviewer_pushback(
    per_agent: list,
    cost_provenance_class: str,
    residual_risks_text: str,
) -> str:
    presentation = StudyPresentation(
        cost_provenance=cost_provenance_class,
        pareto_suppressed=cost_provenance_class == "cost_not_available",
        show_cost_columns=cost_provenance_class != "cost_not_available",
        cost_gap_sensitivity_applicable=cost_provenance_class != "cost_not_available",
        hedge_on_cost_allowed=False,
        source_fixture_rel="",
        source_url="",
        retrieved_at="",
        residual_risks_text=residual_risks_text,
        decision_md_label="",
        cost_recon_data={},
    )
    return audit_summary_section.reviewer_pushback(per_agent, presentation)


_copyable_claim_summary = copyable_claim_summary
_render_verdict_explainer = render_verdict_explainer
_robustness_multiple_comparison = robustness_multiple_comparison
_robustness_errored_policy = robustness_errored_policy
_robustness_cost_threshold = robustness_cost_threshold
_robustness_target_mde = robustness_target_mde
_robustness_cost_provenance = robustness_cost_provenance
_render_audit_summary = render_audit_summary
_render_per_agent_summary = render_per_agent_summary
_render_cost_quality_view = render_cost_quality_view
_render_robustness_review = render_robustness_review
_render_robustness_review_table = render_robustness_review_table


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
    """Render a deterministic markdown report for one declared-claim reanalysis."""
    _validate_report_outcome(study)
    presentation = resolve_study_presentation(study, runs, result, repo_root)
    rendered_at = clock().isoformat()
    parts: list[str] = []

    parts.extend(render_audit_summary(result, study, runs, presentation))

    parts.append("## Study\n")
    parts.append(f"- **id:** `{study.id}`")
    parts.append(f"- **benchmark:** `{study.benchmark}`")
    parts.append(f"- **harness:** `{study.harness}`")
    parts.append(f"- **analysis_mode:** `{study.analysis_mode}`")
    parts.append(f"- **data_observation:** `{study.data_observation}`")
    if len(study.claims) == 1:
        parts.append(f"- **claim:** {study.claims[0].text}")
    else:
        for claim in study.claims:
            parts.append(f"- **claim `{claim.id}`:** {claim.text}")
    parts.append("")

    if study.analysis_mode == "preregistered":
        parts.append("## Provenance\n")
        parts.extend(render_provenance_controlled_evidence(study, runs, repo_root, presentation))
    else:
        parts.extend(render_public_provenance(presentation))

    if presentation.cost_provenance == CostProvenance.AS_REPORTED_ONLY.value:
        parts.extend(render_as_reported_only_caveat(presentation.cost_recon_data))
    if presentation.cost_provenance == CostProvenance.COST_NOT_AVAILABLE.value:
        suppressed_agents = [s.agent_id for s in result.per_agent if s.total_cost_usd is None]
        parts.extend(render_cost_not_available_caveat(suppressed_agents))

    parts.extend(render_per_agent_summary(result, presentation))

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
    mde_per_claim: list[tuple[str, float, float]] = []
    for c in result.claims:
        ctx = claim_context_for_result(c, result, study)
        di = decision_impact(ctx)
        status = claim_status(c.rejects_null, ctx.direction_matches_claim)
        adj = "n/a" if c.adjusted_p_value is None else f"{c.adjusted_p_value:.4f}"
        row = {
            "claim_id": c.claim_id,
            "mode": study.analysis_mode,
            "status": status,
            "effect": format_pp(c.delta_point_estimate),
            "adjusted_result": adj,
            "decision_impact": di,
        }
        if target_mde is not None:
            row["target_mde"] = format_pp(target_mde)
            ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0
            mde_per_claim.append((c.claim_id, ci_half_width, target_mde))
        parts.append(render_claim_row(row))
    parts.append("")

    for c in result.claims:
        ctx = claim_context_for_result(c, result, study)
        parts.extend(
            render_verdict_explainer(
                claim=c,
                presentation=presentation,
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

    for c in result.claims:
        rows = sensitivity_rows_by_claim[c.claim_id]
        baseline_verdict = rows[0].verdict
        parts.append(f"**Verdict sensitivity** — `{c.claim_id}`\n")
        parts.append("| dimension | value | verdict |")
        parts.append("|---|---|---|")
        for r in rows:
            if (
                not presentation.cost_gap_sensitivity_applicable
                and r.dimension == "cost_gap_threshold"
            ):
                verdict_cell = "n/a (cost suppressed)"
            else:
                verdict_cell = r.verdict
                if r.dimension != "baseline" and r.verdict != baseline_verdict:
                    verdict_cell = f"{r.verdict} ← flips"
            parts.append(f"| {r.dimension} | {r.value} | {verdict_cell} |")
        parts.append("")

    parts.extend(render_robustness_review(result, study, sensitivity_rows_by_claim, presentation))
    parts.extend(render_cost_quality_view(result, presentation))

    parts.append("## Residual risks\n")
    parts.append(
        "**Inherited from scouting decision** (verbatim from "
        f"`{presentation.decision_md_label}`):\n"
    )
    parts.append(presentation.residual_risks_text)
    parts.append("")

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
