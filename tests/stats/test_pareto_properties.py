"""Property-based tests for Pareto-frontier invariants."""

from __future__ import annotations

import random

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from eval_audit.stats import pareto_frontier

_SETTINGS = settings(max_examples=100, deadline=2_000)


def _agent_universe(min_agents: int = 2, max_agents: int = 8) -> st.SearchStrategy:
    """A frame with one row per agent: agent_id, success_rate in [0,1], cost > 0."""
    return st.lists(
        st.tuples(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=8),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=min_agents,
        max_size=max_agents,
        unique_by=lambda item: item[0],
    )


def _to_frame(agents: list[tuple[str, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "agent_id": [a for a, _, _ in agents],
            "success_rate": [s for _, s, _ in agents],
            "cost": [c for _, _, c in agents],
        }
    )


def _is_dominated(agent: tuple[str, float, float], others: list) -> bool:
    name, success, cost = agent
    for other_name, other_success, other_cost in others:
        if other_name == name:
            continue
        if (
            other_success >= success
            and other_cost <= cost
            and (other_success > success or other_cost < cost)
        ):
            return True
    return False


@_SETTINGS
@given(_agent_universe())
def test_pareto__every_non_frontier_agent_is_dominated(agents: list) -> None:
    """Every agent NOT in the frontier is strictly dominated by at least one frontier agent."""
    frontier = pareto_frontier(_to_frame(agents), success_col="success_rate", cost_col="cost")
    non_frontier = [a for a in agents if a[0] not in frontier]
    for agent in non_frontier:
        assert _is_dominated(agent, agents), (
            f"agent {agent} excluded from frontier but not strictly dominated"
        )


@_SETTINGS
@given(_agent_universe())
def test_pareto__every_frontier_agent_is_not_dominated(agents: list) -> None:
    """Every agent IN the frontier is NOT strictly dominated by any other agent."""
    frontier = pareto_frontier(_to_frame(agents), success_col="success_rate", cost_col="cost")
    in_frontier = [a for a in agents if a[0] in frontier]
    for agent in in_frontier:
        assert not _is_dominated(agent, agents), f"agent {agent} on frontier but strictly dominated"


@_SETTINGS
@given(_agent_universe(), st.integers(min_value=0, max_value=2**31 - 1))
def test_pareto__closure_under_input_permutation(agents: list, seed: int) -> None:
    """Frontier set is invariant under permutation of input rows."""
    rng = random.Random(seed)
    permuted = list(agents)
    rng.shuffle(permuted)
    a = pareto_frontier(_to_frame(agents), success_col="success_rate", cost_col="cost")
    b = pareto_frontier(_to_frame(permuted), success_col="success_rate", cost_col="cost")
    assert a == b
