"""Per-agent success and cost summaries under declared errored-row policies."""

from __future__ import annotations

from enum import StrEnum

import polars as pl

from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats.errors import CostProvenanceError
from eval_audit.stats.intervals import wilson_interval
from eval_audit.stats.outcomes import success_rate_numeric_expr
from eval_audit.stats.results import AgentSummary


class ErroredRowPolicy(StrEnum):
    headline = "headline"
    graded_only = "graded_only"


def summarize_agent(
    agent_id: str,
    rows: pl.DataFrame,
    alpha: float,
    *,
    policy: ErroredRowPolicy = ErroredRowPolicy.headline,
) -> AgentSummary:
    """Summarize one agent's success rate, Wilson CI, and cost under a row policy."""
    graded = rows.filter(pl.col("outcome_status") == "graded")
    errored = rows.filter(pl.col("outcome_status") == "errored")
    n_graded = graded.height
    n_errored = errored.height if policy == ErroredRowPolicy.headline else 0
    successes = (
        int(
            graded.select(success_rate_numeric_expr().sum().alias("_successes"))[
                "_successes"
            ][0]
        )
        if n_graded
        else 0
    )
    n_total = n_graded + n_errored if policy == ErroredRowPolicy.headline else n_graded
    if n_total > 0:
        point, lo, hi = wilson_interval(successes, n_total, alpha)
    else:
        point, lo, hi = 0.0, 0.0, 1.0

    provenance_values = set(rows["cost_provenance"].to_list())
    if provenance_values == {CostProvenance.COST_NOT_AVAILABLE.value}:
        return AgentSummary(
            agent_id=agent_id,
            n_graded=n_graded,
            n_errored=n_errored,
            success_rate=point,
            success_rate_ci_low=lo,
            success_rate_ci_high=hi,
            total_cost_usd=None,
            cost_per_success_usd=None,
        )
    if CostProvenance.COST_NOT_AVAILABLE.value in provenance_values:
        raise CostProvenanceError(
            f"agent_id={agent_id!r} has mixed cost_provenance including "
            f"'cost_not_available' (cost_provenance={sorted(provenance_values)}); "
            "cost suppression must be whole-agent"
        )

    graded_reconstructed_null_count = graded["reconstructed_per_task_cost_usd"].null_count()
    if 0 < graded_reconstructed_null_count < graded.height:
        provenance = sorted(provenance_values)
        raise CostProvenanceError(
            f"agent_id={agent_id!r} has incomplete reconstructed cost data "
            f"({graded_reconstructed_null_count}/{graded.height} graded rows have "
            f"null reconstructed_per_task_cost_usd; cost_provenance={provenance})"
        )
    if graded.height == 0 or graded_reconstructed_null_count == graded.height:
        if rows["reported_run_total_cost_usd"].null_count() > 0:
            raise CostProvenanceError(
                f"agent_id={agent_id!r} has no reconstructed cost and missing "
                "reported_run_total_cost_usd values"
            )
        per_run = rows.group_by("run_id").agg(
            pl.col("reported_run_total_cost_usd").first().alias("_r")
        )
        total_cost = float(per_run["_r"].sum())
    else:
        total_cost = float(graded["reconstructed_per_task_cost_usd"].sum())
    cost_per_success = total_cost / successes if successes else None
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


def summarize_agents_for_pareto(
    study: StudySpec,
    runs: pl.DataFrame,
    alpha: float,
    *,
    policy: ErroredRowPolicy = ErroredRowPolicy.headline,
) -> pl.DataFrame | None:
    """Return a Pareto-ready frame or None when whole-study cost is suppressed."""
    per_agent_rows: list[dict[str, object]] = []
    for agent_ref in study.agents:
        agent_id = agent_ref.id
        rows = runs.filter(pl.col("agent_id") == agent_id)
        if policy == ErroredRowPolicy.graded_only:
            rows = rows.filter(pl.col("outcome_status") == "graded")
        if rows.height == 0:
            continue
        summary = summarize_agent(agent_id, rows, alpha, policy=policy)
        if summary.total_cost_usd is None:
            return None
        per_agent_rows.append(
            {
                "agent_id": summary.agent_id,
                "success_rate": summary.success_rate,
                "cost": summary.total_cost_usd,
            }
        )
    if not per_agent_rows:
        return None
    return pl.DataFrame(per_agent_rows)
