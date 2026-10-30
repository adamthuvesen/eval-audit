"""Analysis result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from eval_audit.stats.bootstrap import BootstrapResult

ParetoStatus = Literal["computed", "suppressed_cost_not_available"]


@dataclass(frozen=True)
class AnalysisSettings:
    alpha: float = 0.05
    bootstrap_iterations: int = 10_000
    bootstrap_seed: int = 42

    def __post_init__(self) -> None:
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha must be > 0 and < 1")
        if self.bootstrap_iterations < 1:
            raise ValueError("bootstrap_iterations must be >= 1")


@dataclass(frozen=True)
class AgentSummary:
    agent_id: str
    n_graded: int
    n_errored: int
    success_rate: float
    success_rate_ci_low: float
    success_rate_ci_high: float
    total_cost_usd: float | None
    cost_per_success_usd: float | None


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
    treatment_total_cost_usd: float | None
    control_total_cost_usd: float | None
    bootstrap: BootstrapResult


@dataclass(frozen=True)
class AnalysisResult:
    study_id: str
    per_agent: list[AgentSummary]
    claims: list[ClaimResult]
    pareto_frontier: set[str]
    settings: AnalysisSettings
    pareto_status: ParetoStatus = "computed"

    @property
    def bootstrap_seed(self) -> int:
        return self.settings.bootstrap_seed
