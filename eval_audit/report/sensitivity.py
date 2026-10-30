"""Decision presentation for whole-study statistical sensitivity scenarios."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from eval_audit.report.decisions import ClaimContext, decision_impact, direction_matches_claim
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import Verdict
from eval_audit.stats import AnalysisResult, ClaimResult
from eval_audit.stats.sensitivity import (
    SensitivityScenario,
    recompute_scenario,
    sensitivity_scenarios,
)


@dataclass(frozen=True)
class SensitivityRow:
    dimension: str
    value: str
    verdict: Verdict | None
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.verdict is not None


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
        claim.delta_point_estimate if delta_point_estimate is None else delta_point_estimate
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


def _scenario_verdict(
    claim: ClaimResult, scenario: SensitivityScenario, study: StudySpec
) -> Verdict | None:
    if claim.claim_id in scenario.unavailable_claims:
        return None
    perturbed = next(c for c in scenario.result.claims if c.claim_id == claim.claim_id)
    return _baseline_verdict(perturbed, scenario.result, study)


def verdict_with_alpha(
    claim: ClaimResult,
    result: AnalysisResult,
    study: StudySpec,
    *,
    alpha: float,
    runs: pl.DataFrame | None = None,
) -> Verdict:
    """Recompute the p-value decision and confidence intervals at the requested alpha."""
    if runs is None:
        if alpha == result.settings.alpha:
            return _baseline_verdict(claim, result, study)
        raise ValueError("runs are required to recompute confidence intervals at a changed alpha")
    scenario = recompute_scenario(study, runs, result, alpha=alpha)
    verdict = _scenario_verdict(claim, scenario, study)
    assert verdict is not None
    return verdict


def verdict_with_no_correction(
    claim: ClaimResult, result: AnalysisResult, study: StudySpec, *, alpha: float
) -> Verdict:
    if alpha != result.settings.alpha:
        raise ValueError("no-correction sensitivity must use the baseline alpha")
    return decision_impact(
        claim_context_for_result(claim, result, study, rejects_null=claim.raw_p_value <= alpha)
    )


def verdict_with_cost_gap_threshold(
    claim: ClaimResult,
    result: AnalysisResult,
    study: StudySpec,
    *,
    cost_gap_threshold: float,
) -> Verdict:
    return decision_impact(
        claim_context_for_result(claim, result, study), cost_gap_threshold=cost_gap_threshold
    )


def _check_settings(
    result: AnalysisResult, bootstrap_iterations: int | None, bootstrap_seed: int | None
) -> None:
    if (
        bootstrap_iterations is not None
        and bootstrap_iterations != result.settings.bootstrap_iterations
    ) or (bootstrap_seed is not None and bootstrap_seed != result.settings.bootstrap_seed):
        raise ValueError("sensitivity bootstrap settings must match the analysis result")


def verdict_with_errored_excluded(
    claim: ClaimResult,
    runs: pl.DataFrame,
    study: StudySpec,
    result: AnalysisResult,
    *,
    bootstrap_iterations: int | None = None,
    bootstrap_seed: int | None = None,
) -> Verdict | None:
    """Return no verdict when exclusion leaves insufficient paired or Pareto evidence."""
    _check_settings(result, bootstrap_iterations, bootstrap_seed)
    scenario = recompute_scenario(study, runs, result, exclude_errored=True)
    return _scenario_verdict(claim, scenario, study)


def compute_sensitivity_rows(
    claim: ClaimResult,
    runs: pl.DataFrame,
    study: StudySpec,
    result: AnalysisResult,
    *,
    bootstrap_iterations: int | None = None,
    bootstrap_seed: int | None = None,
    scenarios: dict[tuple[str, str], SensitivityScenario] | None = None,
) -> list[SensitivityRow]:
    """Render baseline and perturbations from a shared whole-study scenario set."""
    _check_settings(result, bootstrap_iterations, bootstrap_seed)
    if scenarios is None:
        scenarios = sensitivity_scenarios(study, runs, result)
    rows = [SensitivityRow("baseline", "locked", _baseline_verdict(claim, result, study))]
    for (dimension, value), scenario in scenarios.items():
        rows.append(
            SensitivityRow(
                dimension,
                value,
                _scenario_verdict(claim, scenario, study),
                scenario.unavailable_claims.get(claim.claim_id),
            )
        )
    for threshold in (0.05, 0.20):
        rows.append(
            SensitivityRow(
                "cost_gap_threshold",
                f"{threshold:.2f}",
                verdict_with_cost_gap_threshold(claim, result, study, cost_gap_threshold=threshold),
            )
        )
    return rows


def _baseline_verdict(claim: ClaimResult, result: AnalysisResult, study: StudySpec) -> Verdict:
    return decision_impact(claim_context_for_result(claim, result, study))
