"""Whole-study statistical recomputation for declared sensitivity scenarios."""

from __future__ import annotations

from dataclasses import dataclass, replace

import polars as pl

from eval_audit.schema import StudySpec
from eval_audit.stats.agent_metrics import ErroredRowPolicy, summarize_agent
from eval_audit.stats.analyze import correct_claim_p_values, paired_task_p_value, pareto_status_for
from eval_audit.stats.bootstrap import BootstrapResult, paired_task_bootstrap
from eval_audit.stats.results import AgentSummary, AnalysisResult, ClaimResult, ParetoStatus


@dataclass(frozen=True)
class SensitivityScenario:
    result: AnalysisResult
    unavailable_claims: dict[str, str]


def recompute_scenario(
    study: StudySpec,
    runs: pl.DataFrame,
    baseline: AnalysisResult,
    *,
    alpha: float | None = None,
    exclude_errored: bool = False,
    no_correction: bool = False,
) -> SensitivityScenario:
    """Recompute all agents and claims, preserving the declared correction family.

    Error exclusion changes quality denominators only. Baseline costs under the declared accounting policy
    remain in the Pareto frontier and claim cost comparisons.
    """
    settings = replace(baseline.settings, alpha=baseline.settings.alpha if alpha is None else alpha)
    rows_by_agent = {
        agent.id: runs.filter(pl.col("agent_id") == agent.id) for agent in study.agents
    }
    summaries: list[AgentSummary] = []
    unavailable_agents: set[str] = set()
    for agent in study.agents:
        rows = rows_by_agent[agent.id]
        if exclude_errored and rows.filter(pl.col("outcome_status") == "graded").height == 0:
            unavailable_agents.add(agent.id)
            continue
        summaries.append(
            summarize_agent(
                agent.id,
                rows,
                settings.alpha,
                policy=ErroredRowPolicy.graded_only
                if exclude_errored
                else ErroredRowPolicy.headline,
            )
        )
    frontier: set[str]
    pareto_status: ParetoStatus
    if baseline.pareto_status == "suppressed_cost_not_available":
        frontier, pareto_status = set(), baseline.pareto_status
    else:
        frontier, pareto_status = pareto_status_for(summaries)
    bootstraps: dict[str, BootstrapResult] = {}
    raw_p_pairs: list[tuple[str, float]] = []
    unavailable: dict[str, str] = {}
    for claim in study.claims:
        treatment = rows_by_agent[claim.treatment]
        control = rows_by_agent[claim.control]
        if exclude_errored:
            treatment = treatment.filter(pl.col("outcome_status") == "graded")
            control = control.filter(pl.col("outcome_status") == "graded")
            common_tasks = set(treatment["task_id"].to_list()) & set(control["task_id"].to_list())
            treatment = treatment.filter(pl.col("task_id").is_in(common_tasks))
            control = control.filter(pl.col("task_id").is_in(common_tasks))
            if len(common_tasks) < 2:
                unavailable[claim.id] = (
                    "fewer than two paired graded tasks remain after error exclusion"
                )
        if claim.id in unavailable:
            # Keep the original family size. This placeholder is never a reported test result.
            raw_p_pairs.append((claim.id, 1.0))
            continue
        bootstraps[claim.id] = paired_task_bootstrap(
            treatment,
            control,
            outcome="success",
            n_iter=settings.bootstrap_iterations,
            alpha=settings.alpha,
            seed=settings.bootstrap_seed,
        )
        raw_p_pairs.append((claim.id, paired_task_p_value(treatment, control)))
    corrected = (
        [(cid, p, p, p <= settings.alpha) for cid, p in raw_p_pairs]
        if no_correction
        else correct_claim_p_values(study, raw_p_pairs, alpha=settings.alpha)
    )
    adjusted = {cid: (raw, adj, reject) for cid, raw, adj, reject in corrected}
    claims: list[ClaimResult] = []
    for original in baseline.claims:
        if original.claim_id in unavailable:
            continue
        boot = bootstraps[original.claim_id]
        raw, adj, rejects = adjusted[original.claim_id]
        claims.append(
            replace(
                original,
                delta_point_estimate=boot.delta_point_estimate,
                delta_ci_low=boot.delta_ci_low,
                delta_ci_high=boot.delta_ci_high,
                raw_p_value=raw,
                adjusted_p_value=adj,
                rejects_null=rejects,
                bootstrap=boot,
            )
        )
    if unavailable_agents and pareto_status == "computed":
        # An unknown competitor can change an available frontier for every claim.
        for claim in study.claims:
            unavailable.setdefault(
                claim.id,
                "Pareto frontier unavailable: no graded rows remain for declared agent(s) "
                + ", ".join(sorted(unavailable_agents)),
            )
    return SensitivityScenario(
        AnalysisResult(
            study_id=baseline.study_id,
            per_agent=summaries,
            claims=claims,
            pareto_frontier=frontier,
            settings=settings,
            pareto_status=pareto_status,
        ),
        unavailable,
    )


def sensitivity_scenarios(
    study: StudySpec, runs: pl.DataFrame, baseline: AnalysisResult
) -> dict[tuple[str, str], SensitivityScenario]:
    """Return the statistical perturbations once for the entire claim family."""
    return {
        ("alpha", "0.01"): recompute_scenario(study, runs, baseline, alpha=0.01),
        ("alpha", "0.10"): recompute_scenario(study, runs, baseline, alpha=0.10),
        ("errored_policy", "excluded"): recompute_scenario(
            study, runs, baseline, exclude_errored=True
        ),
        ("correction_method", "none"): recompute_scenario(
            study, runs, baseline, no_correction=True
        ),
    }
