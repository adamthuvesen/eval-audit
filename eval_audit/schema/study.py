"""StudySpec, Claim, and supporting nested models for declared reanalysis."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

_SUPPORTED_V0_COST_METRICS = {
    "reconstructed_per_task_cost_usd",
    "reported_run_total_cost_usd",
    "cost_per_success_usd",
}


class PrimaryOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    unit: Literal["task"]
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


def _study_invariant_errors(study: StudySpec) -> list[str]:
    errors: list[str] = []
    if study.schema_version != 1:
        errors.append(
            f"schema_version must be 1 (got {study.schema_version}); this version of "
            f"eval-audit only supports schema_version=1"
        )
    if not study.agents:
        errors.append("agents must contain at least one entry")
    if not study.claims:
        errors.append("claims must contain at least one entry")
    if study.design.observed_runs_per_agent < 1:
        errors.append(
            "design.observed_runs_per_agent must be >= 1 "
            f"(got {study.design.observed_runs_per_agent})"
        )
    if not 0.0 < study.inference.alpha < 1.0:
        errors.append(f"inference.alpha must be > 0 and < 1 (got {study.inference.alpha})")
    if study.inference.target_mde is not None and not (0.0 < study.inference.target_mde <= 1.0):
        errors.append(
            "inference.target_mde must be > 0 and <= 1 when declared "
            f"(got {study.inference.target_mde})"
        )
    if study.cost.primary_view != "pareto_frontier":
        errors.append(
            f"cost.primary_view must be 'pareto_frontier' in v0 (got {study.cost.primary_view!r})"
        )
    unsupported_cost_metrics = [
        metric for metric in study.cost.metrics if metric not in _SUPPORTED_V0_COST_METRICS
    ]
    if unsupported_cost_metrics:
        errors.append(
            "cost.metrics contains unsupported v0 metric(s): "
            f"{sorted(unsupported_cost_metrics)}; supported metrics are "
            f"{sorted(_SUPPORTED_V0_COST_METRICS)}"
        )
    if study.primary_outcome.name != "success_rate":
        errors.append(
            "primary_outcome.name must be 'success_rate' in v0 "
            f"(got {study.primary_outcome.name!r})"
        )
    if study.primary_outcome.direction != "higher_is_better":
        errors.append(
            "primary_outcome.direction must be 'higher_is_better' in v0 "
            f"(got {study.primary_outcome.direction!r})"
        )
    return errors


def _claim_errors(
    claims: list[Claim],
    *,
    agent_ids: set[str],
    primary_outcome_name: str,
) -> list[str]:
    errors: list[str] = []
    claim_ids_seen: set[str] = set()
    duplicate_claim_ids: set[str] = set()

    for claim in claims:
        if claim.id in claim_ids_seen:
            duplicate_claim_ids.add(claim.id)
        claim_ids_seen.add(claim.id)

        if claim.treatment == claim.control:
            errors.append(
                f"claim {claim.id!r} has identical treatment and control ({claim.treatment!r})"
            )
        for role, agent_id in (
            ("treatment", claim.treatment),
            ("control", claim.control),
        ):
            if agent_id not in agent_ids:
                errors.append(f"claim {claim.id!r} references unknown {role} agent_id {agent_id!r}")

        if claim.outcome != primary_outcome_name:
            errors.append(
                f"claim {claim.id!r} outcome {claim.outcome!r} must match "
                f"primary_outcome.name {primary_outcome_name!r}"
            )
        if claim.outcome != "success_rate":
            errors.append(
                f"claim {claim.id!r} outcome must be 'success_rate' in v0 (got {claim.outcome!r})"
            )

    if duplicate_claim_ids:
        errors.append(f"duplicate claim id(s): {sorted(duplicate_claim_ids)}")
    return errors


class StudySpec(BaseModel):
    """Declared study and its claim family."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
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

    @model_validator(mode="after")
    def _validate_claim_family_and_v0_scope(self) -> StudySpec:
        errors = _study_invariant_errors(self)
        agent_ids = {agent.id for agent in self.agents}
        errors.extend(
            _claim_errors(
                self.claims,
                agent_ids=agent_ids,
                primary_outcome_name=self.primary_outcome.name,
            )
        )

        if errors:
            raise ValueError("; ".join(errors))
        return self

    @classmethod
    def from_yaml(cls, path: Path | str) -> StudySpec:
        """Load and validate a StudySpec from a YAML file.

        Pydantic aggregates every validation error in the raised ValidationError
        rather than bailing on the first.
        """
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        return cls.model_validate(data)
