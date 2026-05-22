"""End-to-end analysis pipeline that consumes a StudySpec and a RunRecord frame."""

from __future__ import annotations

import polars as pl
from scipy.stats import ttest_rel

from eval_audit.schema import StudySpec
from eval_audit.stats.agent_metrics import ErroredRowPolicy, summarize_agent
from eval_audit.stats.bootstrap import BootstrapResult, paired_task_bootstrap
from eval_audit.stats.correction import benjamini_hochberg, holm_bonferroni
from eval_audit.stats.errors import (
    AnalysisInputError,
    CostProvenanceError,
    CrossHarnessComparisonError,
    UnsupportedOutcomeError,
)
from eval_audit.stats.outcomes import success_rate_numeric_expr
from eval_audit.stats.pareto import pareto_frontier
from eval_audit.stats.results import (
    AgentSummary,
    AnalysisResult,
    ClaimResult,
    ParetoStatus,
)

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

    Public so the report-rendering layer can recompute paired p-values for
    sensitivity perturbations against the same statistic the baseline uses.
    """
    success_expr = success_rate_numeric_expr()
    a_means = treatment_rows.group_by("task_id").agg(success_expr.mean().alias("_a"))
    b_means = control_rows.group_by("task_id").agg(success_expr.mean().alias("_b"))
    paired = a_means.join(b_means, on="task_id", how="inner")
    if paired.height < 2:
        return 1.0
    a_vec = paired["_a"].to_numpy()
    b_vec = paired["_b"].to_numpy()
    if (a_vec == b_vec).all():
        return 1.0
    res = ttest_rel(a_vec, b_vec)
    p = float(res.pvalue)
    if p != p:  # NaN guard
        return 1.0
    return p


def _validate_supported_outcome(study: StudySpec) -> str:
    """Return the frame column for the validated v0 outcome contract."""
    if (
        study.primary_outcome.name != "success_rate"
        or study.primary_outcome.direction != "higher_is_better"
    ):
        raise UnsupportedOutcomeError(
            "v0 analysis supports only primary_outcome.name='success_rate' "
            "with direction='higher_is_better'"
        )
    for claim in study.claims:
        if claim.outcome != "success_rate":
            raise UnsupportedOutcomeError(
                f"v0 analysis supports only claim outcome 'success_rate' "
                f"(claim_id={claim.id!r}, outcome={claim.outcome!r})"
            )
    return "success"


def _check_harness_consistency(
    study: StudySpec,
    rows_by_agent: dict[str, pl.DataFrame],
) -> None:
    for claim in study.claims:
        harness_by_agent: dict[str, str] = {}
        for agent_id in (claim.treatment, claim.control):
            rows = rows_by_agent[agent_id]
            if rows.height == 0:
                raise AnalysisInputError(
                    f"agent_id={agent_id!r} has no rows in loaded runs"
                )
            harnesses = sorted(rows["harness"].unique().to_list())
            if len(harnesses) > 1:
                raise AnalysisInputError(
                    f"agent_id={agent_id!r} has rows under multiple harnesses {harnesses}"
                )
            harness_by_agent[agent_id] = harnesses[0]

        treatment_harness = harness_by_agent[claim.treatment]
        control_harness = harness_by_agent[claim.control]
        if treatment_harness != control_harness:
            raise CrossHarnessComparisonError(
                "cross-harness comparison rejected: "
                f"treatment={claim.treatment!r} runs under harness={[treatment_harness]}, "
                f"control={claim.control!r} runs under harness={[control_harness]}"
            )
        for agent_id, observed_harness in harness_by_agent.items():
            if observed_harness != study.harness:
                raise AnalysisInputError(
                    f"agent_id={agent_id!r} runs under harness={observed_harness!r}, "
                    f"but study.harness={study.harness!r}"
                )


def _rows_by_agent(runs: pl.DataFrame, agent_ids: set[str]) -> dict[str, pl.DataFrame]:
    return {
        agent_id: runs.filter(pl.col("agent_id") == agent_id)
        for agent_id in sorted(agent_ids)
    }


def analyze(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
) -> AnalysisResult:
    """Run the declared-claim analysis end-to-end."""
    outcome_col = _validate_supported_outcome(study)
    alpha = study.inference.alpha

    agent_ids = [a.id for a in study.agents]
    claim_agent_ids = {
        agent_id
        for claim in study.claims
        for agent_id in (claim.treatment, claim.control)
    }
    rows_by_agent = _rows_by_agent(runs, set(agent_ids) | claim_agent_ids)

    _check_harness_consistency(study, rows_by_agent)

    per_agent: list[AgentSummary] = []
    by_id: dict[str, AgentSummary] = {}
    for agent_id in agent_ids:
        rows = rows_by_agent[agent_id]
        if rows.height == 0:
            raise AnalysisInputError(
                f"agent_id={agent_id!r} declared in study.agents has no rows in loaded runs"
            )
        summary = summarize_agent(
            agent_id, rows, alpha, policy=ErroredRowPolicy.headline
        )
        per_agent.append(summary)
        by_id[agent_id] = summary

    if any(s.total_cost_usd is None for s in per_agent):
        frontier: set[str] = set()
        pareto_status: ParetoStatus = "suppressed_cost_not_available"
    else:
        per_agent_for_pareto = pl.DataFrame(
            {
                "agent_id": [s.agent_id for s in per_agent],
                "success_rate": [s.success_rate for s in per_agent],
                "cost": [s.total_cost_usd for s in per_agent],
            }
        )
        frontier = pareto_frontier(
            per_agent_for_pareto, success_col="success_rate", cost_col="cost"
        )
        pareto_status = "computed"

    raw_p_pairs: list[tuple[str, float]] = []
    bootstraps: dict[str, BootstrapResult] = {}
    for claim in study.claims:
        treatment_rows = rows_by_agent[claim.treatment]
        control_rows = rows_by_agent[claim.control]
        boot = paired_task_bootstrap(
            treatment_rows,
            control_rows,
            outcome=outcome_col,
            n_iter=bootstrap_iterations,
            alpha=alpha,
            seed=bootstrap_seed,
        )
        bootstraps[claim.id] = boot

        raw_p = paired_task_p_value(treatment_rows, control_rows)
        raw_p_pairs.append((claim.id, raw_p))

    if study.inference.correction_method == "holm_bonferroni":
        corrected = holm_bonferroni(raw_p_pairs, alpha=alpha)
    elif study.inference.correction_method == "benjamini_hochberg":
        corrected = benjamini_hochberg(raw_p_pairs, alpha=alpha)
    else:
        raise ValueError(
            f"unsupported correction_method={study.inference.correction_method!r}"
        )

    by_claim_id = {cid: (rp, ap, rej) for cid, rp, ap, rej in corrected}

    claim_results: list[ClaimResult] = []
    for claim in study.claims:
        boot = bootstraps[claim.id]
        rp, ap, rej = by_claim_id[claim.id]
        claim_results.append(
            ClaimResult(
                claim_id=claim.id,
                text=claim.text,
                treatment=claim.treatment,
                control=claim.control,
                delta_point_estimate=boot.delta_point_estimate,
                delta_ci_low=boot.delta_ci_low,
                delta_ci_high=boot.delta_ci_high,
                raw_p_value=rp,
                adjusted_p_value=ap,
                rejects_null=rej,
                treatment_total_cost_usd=by_id[claim.treatment].total_cost_usd,
                control_total_cost_usd=by_id[claim.control].total_cost_usd,
                bootstrap=boot,
            )
        )

    return AnalysisResult(
        study_id=study.id,
        per_agent=per_agent,
        claims=claim_results,
        pareto_frontier=frontier,
        bootstrap_seed=bootstrap_seed,
        pareto_status=pareto_status,
    )
