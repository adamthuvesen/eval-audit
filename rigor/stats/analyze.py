"""End-to-end analysis pipeline that consumes a StudySpec and a RunRecord frame."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from scipy.stats import norm

from rigor.schema import StudySpec
from rigor.stats.bootstrap import BootstrapResult, paired_task_bootstrap
from rigor.stats.correction import holm_bonferroni
from rigor.stats.intervals import wilson_interval
from rigor.stats.pareto import pareto_frontier


class CrossHarnessComparisonError(RuntimeError):
    """Raised when analyze() is asked to compare agents across different harnesses."""


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


def _two_proportion_z_p(s1: int, n1: int, s2: int, n2: int) -> float:
    """Two-sided two-proportion z-test p-value (pooled)."""
    if n1 == 0 or n2 == 0:
        return 1.0
    p1 = s1 / n1
    p2 = s2 / n2
    p_pool = (s1 + s2) / (n1 + n2)
    se = (p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return float(2 * (1 - norm.cdf(abs(z))))


def _check_harness_consistency(
    study: StudySpec,
    runs: pl.DataFrame,
) -> None:
    for claim in study.claims:
        for agent_id in (claim.treatment, claim.control):
            harnesses = (
                runs.filter(pl.col("agent_id") == agent_id)["harness"].unique().to_list()
            )
            if len(harnesses) > 1:
                raise CrossHarnessComparisonError(
                    f"agent_id={agent_id!r} has rows under multiple harnesses {sorted(harnesses)}"
                )

        treatment_harness_set = set(
            runs.filter(pl.col("agent_id") == claim.treatment)["harness"].to_list()
        )
        control_harness_set = set(
            runs.filter(pl.col("agent_id") == claim.control)["harness"].to_list()
        )
        if treatment_harness_set != control_harness_set:
            raise CrossHarnessComparisonError(
                "cross-harness comparison rejected: "
                f"treatment={claim.treatment!r} runs under harness={sorted(treatment_harness_set)}, "
                f"control={claim.control!r} runs under harness={sorted(control_harness_set)}"
            )


def _agent_summary(
    agent_id: str,
    rows: pl.DataFrame,
    alpha: float,
) -> AgentSummary:
    graded = rows.filter(pl.col("outcome_status") == "graded")
    n_graded = graded.height
    n_errored = rows.height - n_graded
    successes = int(graded["success"].cast(pl.Int64).sum()) if n_graded else 0
    if n_graded > 0:
        point, lo, hi = wilson_interval(successes, n_graded, alpha)
    else:
        point, lo, hi = 0.0, 0.0, 1.0
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
        treatment_rows = runs.filter(
            (pl.col("agent_id") == claim.treatment)
            & (pl.col("outcome_status") == "graded")
        )
        control_rows = runs.filter(
            (pl.col("agent_id") == claim.control)
            & (pl.col("outcome_status") == "graded")
        )
        boot = paired_task_bootstrap(
            treatment_rows,
            control_rows,
            outcome="success",
            n_iter=bootstrap_iterations,
            alpha=alpha,
            seed=bootstrap_seed,
        )
        bootstraps[claim.id] = boot

        t_summary = by_id[claim.treatment]
        c_summary = by_id[claim.control]
        raw_p = _two_proportion_z_p(
            int(round(t_summary.success_rate * t_summary.n_graded)),
            t_summary.n_graded,
            int(round(c_summary.success_rate * c_summary.n_graded)),
            c_summary.n_graded,
        )
        raw_p_pairs.append((claim.id, raw_p))

    if study.inference.correction_method == "holm_bonferroni":
        corrected = holm_bonferroni(raw_p_pairs, alpha=alpha)
    else:
        corrected = [(cid, rp, rp, rp <= alpha) for cid, rp in raw_p_pairs]

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
