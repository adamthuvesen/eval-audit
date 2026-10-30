"""End-to-end analysis pipeline that consumes a StudySpec and a RunRecord frame."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from scipy.stats import ttest_rel

from eval_audit.schema import StudySpec
from eval_audit.stats.agent_metrics import ErroredRowPolicy, summarize_agent
from eval_audit.stats.bootstrap import (
    BootstrapResult,
    paired_outcome_vectors,
    paired_task_bootstrap,
)
from eval_audit.stats.correction import benjamini_hochberg, holm_bonferroni
from eval_audit.stats.errors import (
    AnalysisInputError,
    CostProvenanceError,
    CrossHarnessComparisonError,
    UnsupportedOutcomeError,
)
from eval_audit.stats.pareto import pareto_frontier
from eval_audit.stats.results import (
    AgentSummary,
    AnalysisResult,
    AnalysisSettings,
    ClaimResult,
    ParetoStatus,
)

if TYPE_CHECKING:
    from eval_audit.evidence import PreparedEvidence

__all__ = [
    "AgentSummary",
    "AnalysisInputError",
    "AnalysisResult",
    "ClaimResult",
    "CostProvenanceError",
    "CrossHarnessComparisonError",
    "ParetoStatus",
    "UnsupportedOutcomeError",
    "analyze",
    "paired_task_p_value",
]


def paired_task_p_value(
    treatment_rows: pl.DataFrame,
    control_rows: pl.DataFrame,
) -> float:
    """Paired-task two-sided p-value treating task as the unit of analysis.

    For each task, compute the per-task mean success on each arm (averaging over seeds
    when present), then run a paired t-test on the per-task differences. This respects
    within-task clustering, which a naive 2-proportion z-test would ignore.

    Sensitivity scenarios use the same task pairing and test as baseline analysis.
    """
    a_vec, b_vec = paired_outcome_vectors(treatment_rows, control_rows)
    if len(a_vec) < 2:
        return 1.0
    if (a_vec == b_vec).all():
        return 1.0
    res = ttest_rel(a_vec, b_vec)
    p = float(res.pvalue)
    if p != p:  # NaN guard
        return 1.0
    return p


def _summarize_declared_agents(
    agent_ids: list[str],
    rows_by_agent: dict[str, pl.DataFrame],
    alpha: float,
) -> tuple[list[AgentSummary], dict[str, AgentSummary]]:
    per_agent: list[AgentSummary] = []
    by_id: dict[str, AgentSummary] = {}
    for agent_id in agent_ids:
        rows = rows_by_agent[agent_id]
        if rows.height == 0:
            raise AnalysisInputError(
                f"agent_id={agent_id!r} declared in study.agents has no rows in loaded runs"
            )
        summary = summarize_agent(agent_id, rows, alpha, policy=ErroredRowPolicy.headline)
        per_agent.append(summary)
        by_id[agent_id] = summary
    return per_agent, by_id


def _pareto_status(per_agent: list[AgentSummary]) -> tuple[set[str], ParetoStatus]:
    if any(summary.total_cost_usd is None for summary in per_agent):
        return set(), "suppressed_cost_not_available"
    per_agent_for_pareto = pl.DataFrame(
        {
            "agent_id": [summary.agent_id for summary in per_agent],
            "success_rate": [summary.success_rate for summary in per_agent],
            "cost": [summary.total_cost_usd for summary in per_agent],
        }
    )
    return (
        pareto_frontier(per_agent_for_pareto, success_col="success_rate", cost_col="cost"),
        "computed",
    )


def _claim_statistics(
    study: StudySpec,
    rows_by_agent: dict[str, pl.DataFrame],
    *,
    outcome_col: str,
    alpha: float,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> tuple[dict[str, BootstrapResult], list[tuple[str, float]]]:
    raw_p_pairs: list[tuple[str, float]] = []
    bootstraps: dict[str, BootstrapResult] = {}
    for claim in study.claims:
        treatment_rows = rows_by_agent[claim.treatment]
        control_rows = rows_by_agent[claim.control]
        bootstraps[claim.id] = paired_task_bootstrap(
            treatment_rows,
            control_rows,
            outcome=outcome_col,
            n_iter=bootstrap_iterations,
            alpha=alpha,
            seed=bootstrap_seed,
        )
        raw_p_pairs.append((claim.id, paired_task_p_value(treatment_rows, control_rows)))
    return bootstraps, raw_p_pairs


def _correct_claim_p_values(
    study: StudySpec,
    raw_p_pairs: list[tuple[str, float]],
    *,
    alpha: float,
) -> list[tuple[str, float, float, bool]]:
    if study.inference.correction_method == "holm_bonferroni":
        return holm_bonferroni(raw_p_pairs, alpha=alpha)
    if study.inference.correction_method == "benjamini_hochberg":
        return benjamini_hochberg(raw_p_pairs, alpha=alpha)
    raise ValueError(f"unsupported correction_method={study.inference.correction_method!r}")


def _claim_results(
    study: StudySpec,
    bootstraps: dict[str, BootstrapResult],
    corrected: list[tuple[str, float, float, bool]],
    by_agent_id: dict[str, AgentSummary],
) -> list[ClaimResult]:
    by_claim_id = {cid: (rp, ap, rej) for cid, rp, ap, rej in corrected}
    claim_results: list[ClaimResult] = []
    for claim in study.claims:
        boot = bootstraps[claim.id]
        raw_p_value, adjusted_p_value, rejects_null = by_claim_id[claim.id]
        claim_results.append(
            ClaimResult(
                claim_id=claim.id,
                text=claim.text,
                treatment=claim.treatment,
                control=claim.control,
                delta_point_estimate=boot.delta_point_estimate,
                delta_ci_low=boot.delta_ci_low,
                delta_ci_high=boot.delta_ci_high,
                raw_p_value=raw_p_value,
                adjusted_p_value=adjusted_p_value,
                rejects_null=rejects_null,
                treatment_total_cost_usd=by_agent_id[claim.treatment].total_cost_usd,
                control_total_cost_usd=by_agent_id[claim.control].total_cost_usd,
                bootstrap=boot,
            )
        )
    return claim_results


def analyze(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
) -> AnalysisResult:
    """Run the declared-claim analysis end-to-end."""
    from eval_audit.evidence import prepare_evidence

    evidence = prepare_evidence(study, runs)
    return analyze_prepared(
        evidence,
        settings=AnalysisSettings(
            alpha=evidence.study.inference.alpha,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        ),
    )


def analyze_prepared(evidence: PreparedEvidence, *, settings: AnalysisSettings) -> AnalysisResult:
    """Analyze evidence that passed the shared validation boundary."""
    study = evidence.study
    rows_by_agent = evidence.rows_by_agent
    alpha = settings.alpha
    agent_ids = [agent.id for agent in study.agents]
    per_agent, by_agent_id = _summarize_declared_agents(agent_ids, rows_by_agent, alpha)
    frontier, pareto_status = _pareto_status(per_agent)
    bootstraps, raw_p_pairs = _claim_statistics(
        study,
        rows_by_agent,
        outcome_col="success",
        alpha=alpha,
        bootstrap_iterations=settings.bootstrap_iterations,
        bootstrap_seed=settings.bootstrap_seed,
    )
    corrected = _correct_claim_p_values(study, raw_p_pairs, alpha=alpha)

    return AnalysisResult(
        study_id=study.id,
        per_agent=per_agent,
        claims=_claim_results(study, bootstraps, corrected, by_agent_id),
        pareto_frontier=frontier,
        settings=settings,
        pareto_status=pareto_status,
    )
