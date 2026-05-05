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
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from eval_audit.report.decisions import ClaimContext, decision_impact, direction_matches_claim
from eval_audit.schema import StudySpec
from eval_audit.stats import AnalysisResult, ClaimResult
from eval_audit.stats.bootstrap import paired_task_bootstrap
from eval_audit.stats.intervals import wilson_interval
from eval_audit.stats.pareto import pareto_frontier


@dataclass(frozen=True)
class SensitivityRow:
    dimension: str
    value: str
    verdict: str


# Locked perturbation order. Used by the renderer; do not reorder.
PERTURBATION_ORDER: tuple[tuple[str, str], ...] = (
    ("alpha", "0.01"),
    ("alpha", "0.10"),
    ("errored_policy", "excluded"),
    ("correction_method", "none"),
    ("cost_gap_threshold", "0.05"),
    ("cost_gap_threshold", "0.20"),
)


def _build_context(
    claim: ClaimResult,
    *,
    rejects_null: bool,
    delta_ci_low: float,
    delta_ci_high: float,
    treatment_is_dominated: bool,
    direction_matches_claim: bool,
) -> ClaimContext:
    return ClaimContext(
        rejects_null=rejects_null,
        delta_point_estimate=claim.delta_point_estimate,
        delta_ci_low=delta_ci_low,
        delta_ci_high=delta_ci_high,
        treatment_cost_usd=claim.treatment_total_cost_usd,
        control_cost_usd=claim.control_total_cost_usd,
        treatment_is_dominated=treatment_is_dominated,
        direction_matches_claim=direction_matches_claim,
    )


def _claim_baseline_attrs(
    claim: ClaimResult, result: AnalysisResult, study: StudySpec
) -> tuple[bool, bool]:
    """Return (treatment_is_dominated, direction_matches_claim) for the claim."""
    treatment_is_dominated = claim.treatment not in result.pareto_frontier
    direction_matches = direction_matches_claim(
        study.primary_outcome.direction,
        claim.delta_point_estimate,
    )
    return treatment_is_dominated, direction_matches


def verdict_with_alpha(
    claim: ClaimResult, result: AnalysisResult, study: StudySpec, *, alpha: float
) -> str:
    """Re-derive the verdict against a perturbed alpha threshold.

    Uses the existing raw p-value; no bootstrap re-run.
    """
    treatment_dominated, direction_matches = _claim_baseline_attrs(claim, result, study)
    rejects = claim.adjusted_p_value <= alpha
    ctx = _build_context(
        claim,
        rejects_null=rejects,
        delta_ci_low=claim.delta_ci_low,
        delta_ci_high=claim.delta_ci_high,
        treatment_is_dominated=treatment_dominated,
        direction_matches_claim=direction_matches,
    )
    return decision_impact(ctx)


def verdict_with_no_correction(
    claim: ClaimResult,
    all_claims: list[ClaimResult],
    result: AnalysisResult,
    study: StudySpec,
    *,
    alpha: float,
) -> str:
    """Re-derive the verdict with correction_method = none (use raw p)."""
    treatment_dominated, direction_matches = _claim_baseline_attrs(claim, result, study)
    rejects = claim.raw_p_value <= alpha
    ctx = _build_context(
        claim,
        rejects_null=rejects,
        delta_ci_low=claim.delta_ci_low,
        delta_ci_high=claim.delta_ci_high,
        treatment_is_dominated=treatment_dominated,
        direction_matches_claim=direction_matches,
    )
    # `all_claims` is accepted for symmetry with the corrected path but unused
    # under `correction_method = none`; each claim resolves on its own raw p.
    del all_claims
    return decision_impact(ctx)


def verdict_with_cost_gap_threshold(
    claim: ClaimResult,
    result: AnalysisResult,
    study: StudySpec,
    *,
    cost_gap_threshold: float,
) -> str:
    """Re-derive the verdict with a perturbed cost_gap_threshold."""
    treatment_dominated, direction_matches = _claim_baseline_attrs(claim, result, study)
    ctx = _build_context(
        claim,
        rejects_null=claim.rejects_null,
        delta_ci_low=claim.delta_ci_low,
        delta_ci_high=claim.delta_ci_high,
        treatment_is_dominated=treatment_dominated,
        direction_matches_claim=direction_matches,
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

    This is the only perturbation that re-runs the bootstrap and Wilson CI.
    The Pareto frontier and per-agent costs are recomputed from graded-only
    rows so the verdict is internally consistent with the perturbed denominator.
    """
    alpha = study.inference.alpha
    graded = runs.filter(pl.col("outcome_status") == "graded")

    treatment_rows = graded.filter(pl.col("agent_id") == claim.treatment)
    control_rows = graded.filter(pl.col("agent_id") == claim.control)

    if treatment_rows.height == 0 or control_rows.height == 0:
        # Degenerate perturbation (every row errored on one arm). Fall back to
        # the baseline verdict so the table renders without crashing.
        return decision_impact(
            _build_context(
                claim,
                rejects_null=claim.rejects_null,
                delta_ci_low=claim.delta_ci_low,
                delta_ci_high=claim.delta_ci_high,
                treatment_is_dominated=claim.treatment not in result.pareto_frontier,
                direction_matches_claim=direction_matches_claim(
                    study.primary_outcome.direction,
                    claim.delta_point_estimate,
                ),
            )
        )

    # Recompute paired-task bootstrap on the graded-only frame. Tasks present
    # in only one arm get dropped via the inner join inside the helper.
    common_tasks = set(treatment_rows["task_id"].to_list()) & set(
        control_rows["task_id"].to_list()
    )
    treatment_rows = treatment_rows.filter(pl.col("task_id").is_in(common_tasks))
    control_rows = control_rows.filter(pl.col("task_id").is_in(common_tasks))
    if treatment_rows.height < 2 or control_rows.height < 2:
        return decision_impact(
            _build_context(
                claim,
                rejects_null=claim.rejects_null,
                delta_ci_low=claim.delta_ci_low,
                delta_ci_high=claim.delta_ci_high,
                treatment_is_dominated=claim.treatment not in result.pareto_frontier,
                direction_matches_claim=direction_matches_claim(
                    study.primary_outcome.direction,
                    claim.delta_point_estimate,
                ),
            )
        )

    boot = paired_task_bootstrap(
        treatment_rows,
        control_rows,
        outcome="success",
        n_iter=bootstrap_iterations,
        alpha=alpha,
        seed=bootstrap_seed,
    )

    # Use the bootstrap CI's overlap with zero as the rejection signal — equivalent
    # to a 1-alpha CI test on the bootstrap distribution.
    rejects = not (boot.delta_ci_low <= 0.0 <= boot.delta_ci_high)

    # Pareto dominance: recompute against ALL agents in the study under
    # graded-only stats, so the frontier definition matches analyze() at baseline.
    per_agent_rows: list[dict] = []
    for agent_ref in study.agents:
        agent_id = agent_ref.id
        rows = graded.filter(pl.col("agent_id") == agent_id)
        if rows.height == 0:
            continue
        successes = int(rows["success"].cast(pl.Int64).sum())
        n = rows.height
        rate, _, _ = wilson_interval(successes, n, alpha) if n else (0.0, 0.0, 1.0)
        if rows["reconstructed_per_task_cost_usd"].null_count() == rows.height:
            cost = float(
                rows.group_by("run_id")
                .agg(pl.col("reported_run_total_cost_usd").first().alias("_r"))["_r"]
                .sum()
            )
        else:
            cost = float(rows["reconstructed_per_task_cost_usd"].sum())
        per_agent_rows.append({"agent_id": agent_id, "success_rate": rate, "cost": cost})

    if per_agent_rows:
        frontier = pareto_frontier(
            pl.DataFrame(per_agent_rows), success_col="success_rate", cost_col="cost"
        )
        treatment_is_dominated = claim.treatment not in frontier
    else:
        treatment_is_dominated = False

    direction_matches = direction_matches_claim(
        study.primary_outcome.direction,
        boot.delta_point_estimate,
    )
    ctx = _build_context(
        claim,
        rejects_null=rejects,
        delta_ci_low=boot.delta_ci_low,
        delta_ci_high=boot.delta_ci_high,
        treatment_is_dominated=treatment_is_dominated,
        direction_matches_claim=direction_matches,
    )
    return decision_impact(ctx)


def compute_sensitivity_rows(
    claim: ClaimResult,
    all_claims: list[ClaimResult],
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
                claim, all_claims, result, study, alpha=study.inference.alpha
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
    treatment_dominated, direction_matches = _claim_baseline_attrs(claim, result, study)
    ctx = _build_context(
        claim,
        rejects_null=claim.rejects_null,
        delta_ci_low=claim.delta_ci_low,
        delta_ci_high=claim.delta_ci_high,
        treatment_is_dominated=treatment_dominated,
        direction_matches_claim=direction_matches,
    )
    return decision_impact(ctx)

