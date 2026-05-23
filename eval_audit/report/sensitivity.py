"""Verdict-sensitivity computations for the rendered report.

Each helper takes the original AnalysisResult + StudySpec + a claim and returns
the perturbed `decision_impact` verdict under one specific declaration choice.
The helpers do NOT mutate the inputs; perturbations build their own copies.

Three of the four perturbations are cheap (no re-bootstrap):
  - alpha: re-derives `rejects_null` from the existing raw p-value.
  - correction = none: re-derives the adjusted p as the raw p; for single-claim
    studies this is a trivial no-op.
  - cost_gap_threshold: passes a different kwarg into `decision_impact()`.

The errored-row exclusion perturbation is the only expensive one — it
recomputes per-agent successes/n_total/Wilson CI and re-runs the paired-task
bootstrap on the graded-only frame.

**Rejection basis invariant.** Every perturbation MUST derive ``rejects_null``
from the same statistic the baseline does — the correction-adjusted paired
p-value vs alpha. Using bootstrap CI overlap as a substitute is not
equivalent (the two can disagree near the boundary, e.g. p = 0.0504 with a
CI that excludes zero) and would mean the perturbation reports a verdict
shift caused by switching the test, not by switching the policy.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from eval_audit.report.decisions import ClaimContext, decision_impact, direction_matches_claim
from eval_audit.schema import StudySpec
from eval_audit.stats import AnalysisResult, ClaimResult
from eval_audit.stats.agent_metrics import ErroredRowPolicy, summarize_agents_for_pareto
from eval_audit.stats.analyze import paired_task_p_value
from eval_audit.stats.bootstrap import paired_task_bootstrap
from eval_audit.stats.correction import benjamini_hochberg, holm_bonferroni
from eval_audit.stats.pareto import pareto_frontier


@dataclass(frozen=True)
class SensitivityRow:
    dimension: str
    value: str
    verdict: str


def _build_context(
    claim: ClaimResult,
    result: AnalysisResult,
    study: StudySpec,
    *,
    rejects_null: bool,
    delta_ci_low: float,
    delta_ci_high: float,
    delta_point_estimate: float | None = None,
    treatment_is_dominated: bool | None = None,
    direction_matches: bool | None = None,
) -> ClaimContext:
    point_estimate = (
        claim.delta_point_estimate
        if delta_point_estimate is None
        else delta_point_estimate
    )
    if treatment_is_dominated is None:
        # Under cost suppression the frontier is empty by design; treating absence
        # from the empty frontier as dominance would falsely fire drop_from_shortlist.
        treatment_is_dominated = (
            False
            if result.pareto_status == "suppressed_cost_not_available"
            else claim.treatment not in result.pareto_frontier
        )
    if direction_matches is None:
        direction_matches = direction_matches_claim(
            study.primary_outcome.direction,
            point_estimate,
        )
    return ClaimContext(
        rejects_null=rejects_null,
        delta_point_estimate=point_estimate,
        delta_ci_low=delta_ci_low,
        delta_ci_high=delta_ci_high,
        treatment_cost_usd=claim.treatment_total_cost_usd,
        control_cost_usd=claim.control_total_cost_usd,
        treatment_is_dominated=treatment_is_dominated,
        direction_matches_claim=direction_matches,
    )


def claim_context_for_result(
    claim: ClaimResult,
    result: AnalysisResult,
    study: StudySpec,
    *,
    rejects_null: bool | None = None,
    delta_ci_low: float | None = None,
    delta_ci_high: float | None = None,
    delta_point_estimate: float | None = None,
    treatment_is_dominated: bool | None = None,
    direction_matches: bool | None = None,
) -> ClaimContext:
    """Build the decision context shared by reports and sensitivity checks."""
    return _build_context(
        claim,
        result,
        study,
        rejects_null=claim.rejects_null if rejects_null is None else rejects_null,
        delta_ci_low=claim.delta_ci_low if delta_ci_low is None else delta_ci_low,
        delta_ci_high=claim.delta_ci_high if delta_ci_high is None else delta_ci_high,
        delta_point_estimate=delta_point_estimate,
        treatment_is_dominated=treatment_is_dominated,
        direction_matches=direction_matches,
    )


def verdict_with_alpha(
    claim: ClaimResult, result: AnalysisResult, study: StudySpec, *, alpha: float
) -> str:
    """Re-derive the verdict against a perturbed alpha threshold.

    Uses the existing raw p-value; no bootstrap re-run.
    """
    rejects = claim.adjusted_p_value <= alpha
    ctx = claim_context_for_result(
        claim,
        result,
        study,
        rejects_null=rejects,
    )
    return decision_impact(ctx)


def verdict_with_no_correction(
    claim: ClaimResult,
    result: AnalysisResult,
    study: StudySpec,
    *,
    alpha: float,
) -> str:
    """Re-derive the verdict with correction_method = none (use raw p)."""
    rejects = claim.raw_p_value <= alpha
    ctx = claim_context_for_result(
        claim,
        result,
        study,
        rejects_null=rejects,
    )
    return decision_impact(ctx)


def verdict_with_cost_gap_threshold(
    claim: ClaimResult,
    result: AnalysisResult,
    study: StudySpec,
    *,
    cost_gap_threshold: float,
) -> str:
    """Re-derive the verdict with a perturbed cost_gap_threshold."""
    ctx = claim_context_for_result(
        claim,
        result,
        study,
    )
    return decision_impact(ctx, cost_gap_threshold=cost_gap_threshold)


def verdict_with_errored_excluded(
    claim: ClaimResult,
    runs: pl.DataFrame,
    study: StudySpec,
    result: AnalysisResult,
    *,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> str:
    """Re-derive the verdict with errored rows excluded from the denominator.

    No-op short-circuit: if neither arm in the claim has any errored rows,
    excluding errored rows is by definition a no-op, and the perturbation
    returns the baseline verdict.

    With at least one errored row on either arm, the perturbation:

    1. Recomputes the paired-task p-value on the graded-only frame.
    2. Re-applies the study's correction method across the claim family,
       substituting the perturbed claim's raw p so the adjusted p reflects
       the same correction the baseline used.
    3. Recomputes the bootstrap CI for the verdict's CI-crosses-zero
       branch, the per-agent Wilson summary for the Pareto frontier, and
       per-agent cost from the graded-only frame.

    The key invariant: ``rejects_null`` is derived from
    ``adjusted_p_value <= alpha`` — the same statistic the baseline uses.
    """
    alpha = study.inference.alpha
    n_errored_in_claim = (
        runs.filter(
            pl.col("agent_id").is_in([claim.treatment, claim.control])
            & (pl.col("outcome_status") == "errored")
        ).height
    )
    if n_errored_in_claim == 0:
        # No-op perturbation: excluding zero rows leaves the denominator,
        # paired p, bootstrap CI, Pareto frontier, and costs unchanged.
        return _baseline_verdict(claim, result, study)

    graded = runs.filter(pl.col("outcome_status") == "graded")

    treatment_rows = graded.filter(pl.col("agent_id") == claim.treatment)
    control_rows = graded.filter(pl.col("agent_id") == claim.control)

    if treatment_rows.height == 0 or control_rows.height == 0:
        # Degenerate perturbation (every row errored on one arm). Fall back to
        # the baseline verdict so the table renders without crashing.
        return _baseline_verdict(claim, result, study)

    # Recompute paired-task bootstrap on the graded-only frame after explicitly
    # aligning task sets; the bootstrap helper refuses mismatched task ids.
    common_tasks = set(treatment_rows["task_id"].to_list()) & set(
        control_rows["task_id"].to_list()
    )
    treatment_rows = treatment_rows.filter(pl.col("task_id").is_in(common_tasks))
    control_rows = control_rows.filter(pl.col("task_id").is_in(common_tasks))
    if treatment_rows.height < 2 or control_rows.height < 2:
        return _baseline_verdict(claim, result, study)

    boot = paired_task_bootstrap(
        treatment_rows,
        control_rows,
        outcome="success",
        n_iter=bootstrap_iterations,
        alpha=alpha,
        seed=bootstrap_seed,
    )

    perturbed_raw_p = paired_task_p_value(treatment_rows, control_rows)
    raw_p_pairs: list[tuple[str, float]] = []
    for c in result.claims:
        rp = perturbed_raw_p if c.claim_id == claim.claim_id else c.raw_p_value
        raw_p_pairs.append((c.claim_id, rp))
    if study.inference.correction_method == "holm_bonferroni":
        corrected = holm_bonferroni(raw_p_pairs, alpha=alpha)
    elif study.inference.correction_method == "benjamini_hochberg":
        corrected = benjamini_hochberg(raw_p_pairs, alpha=alpha)
    else:
        # Should never happen given the StudySpec validator; fall back conservatively.
        corrected = [
            (cid, rp, rp, rp <= alpha) for (cid, rp) in raw_p_pairs
        ]
    perturbed_adj_p = next(
        adj for (cid, _rp, adj, _rej) in corrected if cid == claim.claim_id
    )
    rejects = perturbed_adj_p <= alpha

    # Pareto dominance: recompute against ALL agents in the study under
    # graded-only stats, so the frontier definition matches analyze() at baseline.
    # Skip the recompute under cost suppression; matches analyze()'s behavior.
    if result.pareto_status == "suppressed_cost_not_available":
        treatment_is_dominated = False
    else:
        per_agent_for_pareto = summarize_agents_for_pareto(
            study,
            runs,
            alpha,
            policy=ErroredRowPolicy.graded_only,
        )
        if per_agent_for_pareto is None:
            treatment_is_dominated = False
        else:
            frontier = pareto_frontier(
                per_agent_for_pareto,
                success_col="success_rate",
                cost_col="cost",
            )
            treatment_is_dominated = claim.treatment not in frontier

    direction_matches = direction_matches_claim(
        study.primary_outcome.direction,
        boot.delta_point_estimate,
    )
    ctx = claim_context_for_result(
        claim,
        result,
        study,
        rejects_null=rejects,
        delta_ci_low=boot.delta_ci_low,
        delta_ci_high=boot.delta_ci_high,
        delta_point_estimate=boot.delta_point_estimate,
        treatment_is_dominated=treatment_is_dominated,
        direction_matches=direction_matches,
    )
    return decision_impact(ctx)


def compute_sensitivity_rows(
    claim: ClaimResult,
    runs: pl.DataFrame,
    study: StudySpec,
    result: AnalysisResult,
    *,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> list[SensitivityRow]:
    """Return the seven rows (baseline + six perturbations) for one claim."""
    baseline = SensitivityRow(
        dimension="baseline",
        value="locked",
        verdict=_baseline_verdict(claim, result, study),
    )

    rows: list[SensitivityRow] = [baseline]

    rows.append(
        SensitivityRow("alpha", "0.01", verdict_with_alpha(claim, result, study, alpha=0.01))
    )
    rows.append(
        SensitivityRow("alpha", "0.10", verdict_with_alpha(claim, result, study, alpha=0.10))
    )
    rows.append(
        SensitivityRow(
            "errored_policy",
            "excluded",
            verdict_with_errored_excluded(
                claim,
                runs,
                study,
                result,
                bootstrap_iterations=bootstrap_iterations,
                bootstrap_seed=bootstrap_seed,
            ),
        )
    )
    rows.append(
        SensitivityRow(
            "correction_method",
            "none",
            verdict_with_no_correction(
                claim, result, study, alpha=study.inference.alpha
            ),
        )
    )
    rows.append(
        SensitivityRow(
            "cost_gap_threshold",
            "0.05",
            verdict_with_cost_gap_threshold(claim, result, study, cost_gap_threshold=0.05),
        )
    )
    rows.append(
        SensitivityRow(
            "cost_gap_threshold",
            "0.20",
            verdict_with_cost_gap_threshold(claim, result, study, cost_gap_threshold=0.20),
        )
    )
    return rows


def _baseline_verdict(claim: ClaimResult, result: AnalysisResult, study: StudySpec) -> str:
    """Recompute the baseline verdict from claim + result, using default thresholds.

    This MUST match the verdict the renderer's claim row reports — the spec
    pins this invariant.
    """
    ctx = claim_context_for_result(
        claim,
        result,
        study,
    )
    return decision_impact(ctx)
