"""End-to-end analysis pipeline that consumes a StudySpec and a RunRecord frame."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from scipy.stats import ttest_rel

from eval_audit.schema import StudySpec
from eval_audit.stats.bootstrap import BootstrapResult, paired_task_bootstrap
from eval_audit.stats.correction import benjamini_hochberg, holm_bonferroni
from eval_audit.stats.intervals import wilson_interval
from eval_audit.stats.outcomes import success_rate_numeric_expr
from eval_audit.stats.pareto import pareto_frontier


class CrossHarnessComparisonError(RuntimeError):
    """Raised when analyze() is asked to compare agents across different harnesses."""


class UnsupportedOutcomeError(ValueError):
    """Raised when analyze() receives an outcome declaration outside v0 support."""


class CostProvenanceError(ValueError):
    """Raised when cost provenance is too incomplete for decision reporting."""


@dataclass(frozen=True)
class AgentSummary:
    agent_id: str
    n_graded: int
    n_errored: int
    success_rate: float
    success_rate_ci_low: float
    success_rate_ci_high: float
    total_cost_usd: float
    cost_per_success_usd: float


@dataclass(frozen=True)
class ClaimResult:
    claim_id: str
    text: str
    treatment: str
    control: str
    delta_point_estimate: float
    delta_ci_low: float
    delta_ci_high: float
    raw_p_value: float
    adjusted_p_value: float
    rejects_null: bool
    treatment_total_cost_usd: float
    control_total_cost_usd: float
    bootstrap: BootstrapResult


@dataclass(frozen=True)
class AnalysisResult:
    study_id: str
    per_agent: list[AgentSummary]
    claims: list[ClaimResult]
    pareto_frontier: set[str]
    bootstrap_seed: int


def _paired_task_p_value(
    treatment_rows: pl.DataFrame,
    control_rows: pl.DataFrame,
) -> float:
    """Paired-task two-sided p-value treating task as the unit of analysis.

    For each task, compute the per-task mean success on each arm (averaging over seeds
    when present), then run a paired t-test on the per-task differences. This respects
    within-task clustering, which a naive 2-proportion z-test would ignore.
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
    runs: pl.DataFrame,
) -> None:
    for claim in study.claims:
        harness_by_agent: dict[str, str] = {}
        for agent_id in (claim.treatment, claim.control):
            rows = runs.filter(pl.col("agent_id") == agent_id)
            if rows.height == 0:
                raise CrossHarnessComparisonError(
                    f"agent_id={agent_id!r} has no rows in loaded runs"
                )
            harnesses = sorted(rows["harness"].unique().to_list())
            if len(harnesses) > 1:
                raise CrossHarnessComparisonError(
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
                raise CrossHarnessComparisonError(
                    f"agent_id={agent_id!r} runs under harness={observed_harness!r}, "
                    f"but study.harness={study.harness!r}"
                )


def _agent_summary(
    agent_id: str,
    rows: pl.DataFrame,
    alpha: float,
) -> AgentSummary:
    graded = rows.filter(pl.col("outcome_status") == "graded")
    errored = rows.filter(pl.col("outcome_status") == "errored")
    n_graded = graded.height
    n_errored = errored.height
    n_total = n_graded + n_errored
    successes = (
        int(
            graded.select(success_rate_numeric_expr().sum().alias("_successes"))[
                "_successes"
            ][0]
        )
        if n_graded
        else 0
    )
    if n_total > 0:
        point, lo, hi = wilson_interval(successes, n_total, alpha)
    else:
        point, lo, hi = 0.0, 0.0, 1.0
    # Per design.md: errored rows have None reconstructed cost; sum() ignores None,
    # so the reconstructed total covers graded rows only — which is the correct
    # numerator. For as_reported_only studies, reconstructed sums to 0 across the
    # frame; the renderer falls back to reported_run_total_cost_usd in that path.
    reconstructed_null_count = rows["reconstructed_per_task_cost_usd"].null_count()
    if 0 < reconstructed_null_count < rows.height:
        provenance = sorted(set(rows["cost_provenance"].to_list()))
        raise CostProvenanceError(
            f"agent_id={agent_id!r} has incomplete reconstructed cost data "
            f"({reconstructed_null_count}/{rows.height} null reconstructed_per_task_cost_usd; "
            f"cost_provenance={provenance})"
        )
    if reconstructed_null_count == rows.height:
        # No reconstructed cost available (as_reported_only path): fall back to
        # the per-(agent, run) reported run total so cost_per_success has a value.
        if rows["reported_run_total_cost_usd"].null_count() > 0:
            raise CostProvenanceError(
                f"agent_id={agent_id!r} has no reconstructed cost and missing "
                "reported_run_total_cost_usd values"
            )
        per_run = (
            rows.group_by("run_id")
            .agg(pl.col("reported_run_total_cost_usd").first().alias("_r"))
        )
        total_cost = float(per_run["_r"].sum())
    else:
        total_cost = float(rows["reconstructed_per_task_cost_usd"].sum())
    cost_per_success = total_cost / successes if successes else float("inf")
    return AgentSummary(
        agent_id=agent_id,
        n_graded=n_graded,
        n_errored=n_errored,
        success_rate=point,
        success_rate_ci_low=lo,
        success_rate_ci_high=hi,
        total_cost_usd=total_cost,
        cost_per_success_usd=cost_per_success,
    )


def analyze(
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
) -> AnalysisResult:
    """Run the declared-claim analysis end-to-end."""
    outcome_col = _validate_supported_outcome(study)
    # Eager pre-check: refuse cross-harness comparisons before any compute.
    _check_harness_consistency(study, runs)

    alpha = study.inference.alpha

    agent_ids = [a.id for a in study.agents]
    per_agent: list[AgentSummary] = []
    by_id: dict[str, AgentSummary] = {}
    for agent_id in agent_ids:
        rows = runs.filter(pl.col("agent_id") == agent_id)
        summary = _agent_summary(agent_id, rows, alpha)
        per_agent.append(summary)
        by_id[agent_id] = summary

    per_agent_for_pareto = pl.DataFrame(
        {
            "agent_id": [s.agent_id for s in per_agent],
            "success_rate": [s.success_rate for s in per_agent],
            "cost": [s.total_cost_usd for s in per_agent],
        }
    )
    frontier = pareto_frontier(per_agent_for_pareto, success_col="success_rate", cost_col="cost")

    raw_p_pairs: list[tuple[str, float]] = []
    bootstraps: dict[str, BootstrapResult] = {}
    for claim in study.claims:
        # Include errored rows: per the errored-row denominator policy, the bootstrap
        # treats errored rows as success=0 in the per-task aggregation so paired task
        # sets stay aligned even when one arm errored on tasks the other graded.
        treatment_rows = runs.filter(pl.col("agent_id") == claim.treatment)
        control_rows = runs.filter(pl.col("agent_id") == claim.control)
        boot = paired_task_bootstrap(
            treatment_rows,
            control_rows,
            outcome=outcome_col,
            n_iter=bootstrap_iterations,
            alpha=alpha,
            seed=bootstrap_seed,
        )
        bootstraps[claim.id] = boot

        raw_p = _paired_task_p_value(treatment_rows, control_rows)
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
    )
