"""Pareto-frontier identification on (success, cost)."""

from __future__ import annotations

import polars as pl


def pareto_frontier(
    per_agent: pl.DataFrame,
    *,
    success_col: str,
    cost_col: str,
) -> set[str]:
    """Return the agent_ids on the Pareto frontier of (success higher, cost lower).

    An agent A is on the frontier iff no other agent has both
    success >= A.success AND cost <= A.cost with at least one strict inequality.
    Ties (same success AND same cost) are both retained.
    """
    rows = per_agent.select("agent_id", success_col, cost_col).rows()
    frontier: set[str] = set()
    for agent, success, cost in rows:
        dominated = False
        for other_agent, other_success, other_cost in rows:
            if other_agent == agent:
                continue
            if (
                other_success >= success
                and other_cost <= cost
                and (other_success > success or other_cost < cost)
            ):
                dominated = True
                break
        if not dominated:
            frontier.add(agent)
    return frontier
