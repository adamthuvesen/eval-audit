"""Canonical task-level observation for a single agent run."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from eval_audit.schema.enums import CostProvenance, OutcomeStatus


class RunRecord(BaseModel):
    """One task-level observation within a single agent run.

    Field semantics inherit from the locked semantic-role vocabulary in the
    `exhibit-a-scouting` capability spec; see scouting/exhibit-a-decision.md.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    agent_id: str
    model_id: str
    harness: str
    run_id: str
    task_id: str
    task_category: str | None = None
    seed: int | None = None
    success: bool | None
    partial_credit: float | int | bool | None = None
    outcome_status: OutcomeStatus
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    tokens_in_by_model: dict[str, int]
    tokens_out_by_model: dict[str, int]
    latency_s: float | None = Field(default=None, ge=0)
    timestamp: datetime | None = None
    reconstructed_per_task_cost_usd: float | None = Field(ge=0)
    reported_run_total_cost_usd: float | None = Field(default=None, ge=0)
    cost_provenance: CostProvenance
    rerun_metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("tokens_in_by_model", "tokens_out_by_model")
    @classmethod
    def _token_breakdowns_are_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        negative_models = [model for model, tokens in value.items() if tokens < 0]
        if negative_models:
            raise ValueError(
                "token breakdown values must be non-negative "
                f"(model(s): {sorted(negative_models)})"
            )
        return value

    @model_validator(mode="after")
    def _outcome_status_matches_outcome_fields(self) -> RunRecord:
        if self.outcome_status == OutcomeStatus.GRADED and self.success is None:
            raise ValueError(
                "graded outcome_status requires non-null success "
                "(field=success, outcome_status=graded)"
            )
        if self.outcome_status == OutcomeStatus.ERRORED:
            errors: list[str] = []
            if self.success is not None:
                errors.append("success must be null when outcome_status=errored")
            if self.partial_credit is not None:
                errors.append("partial_credit must be null when outcome_status=errored")
            if errors:
                raise ValueError("; ".join(errors))
        return self

    @model_validator(mode="after")
    def _reconciled_provenance_requires_reconstructed_cost(self) -> RunRecord:
        if (
            self.cost_provenance == CostProvenance.RECONCILED
            and self.reconstructed_per_task_cost_usd is None
        ):
            raise ValueError(
                "cost_provenance='reconciled' requires non-null reconstructed_per_task_cost_usd "
                "(fields: cost_provenance, reconstructed_per_task_cost_usd)"
            )
        return self

    @model_validator(mode="after")
    def _cost_not_available_requires_null_cost_fields(self) -> RunRecord:
        if self.cost_provenance != CostProvenance.COST_NOT_AVAILABLE:
            return self
        errors: list[str] = []
        if self.reconstructed_per_task_cost_usd is not None:
            errors.append(
                "cost_provenance='cost_not_available' requires null reconstructed_per_task_cost_usd "
                "(fields: cost_provenance, reconstructed_per_task_cost_usd)"
            )
        if self.reported_run_total_cost_usd is not None:
            errors.append(
                "cost_provenance='cost_not_available' requires null reported_run_total_cost_usd "
                "(fields: cost_provenance, reported_run_total_cost_usd)"
            )
        if errors:
            raise ValueError("; ".join(errors))
        return self
