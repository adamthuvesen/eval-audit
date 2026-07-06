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
from eval_audit.report.sections.audit_summary import (
    render_audit_summary,
)
from eval_audit.report.sections.claims_table import (
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
    render_robustness_review,
)
from eval_audit.report.sensitivity import (
    SensitivityRow,
    claim_context_for_result,
    compute_sensitivity_rows,
)
from eval_audit.report.summary import claim_status
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats import AnalysisResult, analyze


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


def _render_study_section(study: StudySpec) -> list[str]:
    parts = [
        "## Study\n",
        f"- **id:** `{study.id}`",
        f"- **benchmark:** `{study.benchmark}`",
        f"- **harness:** `{study.harness}`",
        f"- **analysis_mode:** `{study.analysis_mode}`",
        f"- **data_observation:** `{study.data_observation}`",
    ]
    if len(study.claims) == 1:
        parts.append(f"- **claim:** {study.claims[0].text}")
    else:
        for claim in study.claims:
            parts.append(f"- **claim `{claim.id}`:** {claim.text}")
    parts.append("")
    return parts


def _render_provenance_and_cost_caveats(
    result: AnalysisResult,
    study: StudySpec,
    runs: pl.DataFrame,
    repo_root: Path,
    presentation: StudyPresentation,
) -> list[str]:
    parts: list[str] = []
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
    return parts


def _render_claims_table(
    result: AnalysisResult,
    study: StudySpec,
) -> tuple[list[str], list[tuple[str, float, float]]]:
    parts = ["## Claims\n"]
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
    for claim in result.claims:
        ctx = claim_context_for_result(claim, result, study)
        row = {
            "claim_id": claim.claim_id,
            "mode": study.analysis_mode,
            "status": claim_status(claim.rejects_null, ctx.direction_matches_claim),
            "effect": format_pp(claim.delta_point_estimate),
            "adjusted_result": (
                "n/a" if claim.adjusted_p_value is None else f"{claim.adjusted_p_value:.4f}"
            ),
            "decision_impact": decision_impact(ctx),
        }
        if target_mde is not None:
            row["target_mde"] = format_pp(target_mde)
            ci_half_width = (claim.delta_ci_high - claim.delta_ci_low) / 2.0
            mde_per_claim.append((claim.claim_id, ci_half_width, target_mde))
        parts.append(render_claim_row(row))
    parts.append("")
    return parts, mde_per_claim


def _render_claim_explainers(
    result: AnalysisResult,
    study: StudySpec,
    presentation: StudyPresentation,
    evidence_readiness: str,
) -> list[str]:
    parts: list[str] = []
    for claim in result.claims:
        ctx = claim_context_for_result(claim, result, study)
        parts.extend(
            render_verdict_explainer(
                claim=claim,
                presentation=presentation,
                evidence_readiness=evidence_readiness,
                ctx=ctx,
            )
        )
    return parts


def _mde_context_wording(diff_pp: float) -> str:
    if diff_pp < -0.5:
        return (
            "the study has resolution finer than the declared MDE; "
            "an effect of this size would be detectable"
        )
    if abs(diff_pp) <= 0.5:
        return (
            "the study sits at the declared MDE; "
            "an effect of exactly this size sits on the detection boundary"
        )
    return (
        "the study has resolution coarser than the declared MDE; "
        "an effect at the declared MDE would not be reliably detected without more data"
    )


def _render_mde_context(mde_per_claim: list[tuple[str, float, float]]) -> list[str]:
    if not mde_per_claim:
        return []
    parts = ["**MDE context**\n"]
    for claim_id, half_width, mde in mde_per_claim:
        diff_pp = (half_width - mde) * 100
        parts.append(
            f"- `{claim_id}`: bootstrap CI half-width = {half_width * 100:.2f} pp "
            f"vs target_mde = {mde * 100:.2f} pp — {_mde_context_wording(diff_pp)}."
        )
    parts.append("")
    return parts


def _sensitivity_rows_by_claim(
    result: AnalysisResult,
    runs: pl.DataFrame,
    study: StudySpec,
    *,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> dict[str, list[SensitivityRow]]:
    return {
        claim.claim_id: compute_sensitivity_rows(
            claim,
            runs,
            study,
            result,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        )
        for claim in result.claims
    }


def _render_verdict_sensitivity(
    result: AnalysisResult,
    sensitivity_rows_by_claim: dict[str, list[SensitivityRow]],
    presentation: StudyPresentation,
) -> list[str]:
    parts: list[str] = []
    for claim in result.claims:
        rows = sensitivity_rows_by_claim[claim.claim_id]
        baseline_verdict = rows[0].verdict
        parts.append(f"**Verdict sensitivity** — `{claim.claim_id}`\n")
        parts.append("| dimension | value | verdict |")
        parts.append("|---|---|---|")
        for row in rows:
            if (
                not presentation.cost_gap_sensitivity_applicable
                and row.dimension == "cost_gap_threshold"
            ):
                verdict_cell = "n/a (cost suppressed)"
            else:
                verdict_cell = row.verdict
                if row.dimension != "baseline" and row.verdict != baseline_verdict:
                    verdict_cell = f"{row.verdict} ← flips"
            parts.append(f"| {row.dimension} | {row.value} | {verdict_cell} |")
        parts.append("")
    return parts


def _render_residual_risks(presentation: StudyPresentation) -> list[str]:
    return [
        "## Residual risks\n",
        "**Inherited from scouting decision** (verbatim from "
        f"`{presentation.decision_md_label}`):\n",
        presentation.residual_risks_text,
        "",
    ]


def _render_reproducibility_footer(
    *,
    rendered_at: str,
    git_commit: str,
    fixture_sha256: str,
    bootstrap_seed: int,
    evidence_readiness: str,
    check_sha256: str,
) -> list[str]:
    return [
        "## Reproducibility footer\n",
        f"- **rendered_at:** `{rendered_at}`",
        f"- **git_commit:** `{git_commit}`",
        f"- **fixture_sha256:** `{fixture_sha256}`",
        f"- **bootstrap_seed:** `{bootstrap_seed}`",
        f"- **evidence_readiness:** `{evidence_readiness}`",
        f"- **check_sha256:** `{check_sha256}`",
        "",
    ]


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
    parts.extend(_render_study_section(study))
    parts.extend(_render_provenance_and_cost_caveats(result, study, runs, repo_root, presentation))
    parts.extend(render_per_agent_summary(result, presentation))
    claim_parts, mde_per_claim = _render_claims_table(result, study)
    parts.extend(claim_parts)
    parts.extend(_render_claim_explainers(result, study, presentation, evidence_readiness))
    parts.extend(_render_mde_context(mde_per_claim))

    sensitivity_rows_by_claim = _sensitivity_rows_by_claim(
        result,
        runs,
        study,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    parts.extend(_render_verdict_sensitivity(result, sensitivity_rows_by_claim, presentation))

    parts.extend(render_robustness_review(result, study, sensitivity_rows_by_claim, presentation))
    parts.extend(render_cost_quality_view(result, presentation))
    parts.extend(_render_residual_risks(presentation))
    parts.extend(
        _render_reproducibility_footer(
            rendered_at=rendered_at,
            git_commit=git_commit,
            fixture_sha256=fixture_sha256,
            bootstrap_seed=result.bootstrap_seed,
            evidence_readiness=evidence_readiness,
            check_sha256=check_sha256,
        )
    )

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
