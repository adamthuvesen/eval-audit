"""StudySpec, Claim, and supporting nested models for declared reanalysis."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict


class PrimaryOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    unit: str
    direction: Literal["higher_is_better", "lower_is_better"]


class AgentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str


class Design(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_sampling: str
    run_strategy: str
    observed_runs_per_agent: int
    rerun_policy: str


class Inference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alpha: float = 0.05
    correction_method: Literal["holm_bonferroni", "benjamini_hochberg"]
    comparison_family: Literal["declared_claims", "exploratory"]
    target_mde: float | None = None


class CostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[str]
    primary_view: Literal["pareto_frontier", "summary_table"]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    treatment: str
    control: str
    outcome: str


class StudySpec(BaseModel):
    """Declared study and its claim family."""

    model_config = ConfigDict(extra="forbid")

    id: str
    benchmark: str
    analysis_mode: Literal["preregistered", "declared_reanalysis", "exploratory"]
    data_observation: Literal["unseen", "summary_seen", "full_seen"]
    harness: str
    primary_outcome: PrimaryOutcome
    agents: list[AgentRef]
    design: Design
    inference: Inference
    cost: CostConfig
    claims: list[Claim]

    @classmethod
    def from_yaml(cls, path: Path | str) -> StudySpec:
        """Load and validate a StudySpec from a YAML file.

        Pydantic aggregates every validation error in the raised ValidationError
        rather than bailing on the first.
        """
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        return cls.model_validate(data)
