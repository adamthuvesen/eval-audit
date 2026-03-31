"""Canonical task-level observation for a single agent run."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from rigor.schema.enums import CostProvenance, OutcomeStatus


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
    tokens_in: int
    tokens_out: int
    tokens_in_by_model: dict[str, int]
    tokens_out_by_model: dict[str, int]
    latency_s: float | None = None
    timestamp: datetime | None = None
    reconstructed_per_task_cost_usd: float | None
    reported_run_total_cost_usd: float | None = None
    cost_provenance: CostProvenance
    rerun_metadata: dict[str, str] = {}

    @model_validator(mode="after")
    def _graded_rows_have_success(self) -> RunRecord:
        if self.outcome_status == OutcomeStatus.GRADED and self.success is None:
            raise ValueError(
                "graded outcome_status requires non-null success "
                "(field=success, outcome_status=graded)"
            )
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
