"""Pydantic models for completed audit summary.json artifacts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VerdictExplanationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: str
    first_matching_branch: str
    conditions: dict[str, bool | float | None]
    suppressed_branches: list[str]
    summary: str


class ClaimSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: str
    claim_id: str
    claim_text: str
    treatment: str
    control: str
    verdict: str
    claim_status: str
    readiness: str
    delta: float
    ci_low: float
    ci_high: float
    adjusted_p_value: float | None
    rejects_null: bool
    paired_tasks: int
    cost_provenance: str
    treatment_total_cost_usd: float | None
    control_total_cost_usd: float | None
    cost_caveat: str
    verdict_explanation: VerdictExplanationPayload
    human_summary: str
    artifact_paths: dict[str, str]
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


class AuditSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    study_id: str
    readiness: str
    artifact_paths: dict[str, str]
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    claims: list[ClaimSummary]

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
