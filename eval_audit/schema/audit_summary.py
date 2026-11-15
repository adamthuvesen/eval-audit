"""Pydantic models for completed audit summary.json artifacts."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from eval_audit.schema.artifacts import ARTIFACT_FILES
from eval_audit.schema.enums import ReadinessStatus, Verdict

FiniteNumber = Annotated[float, Field(allow_inf_nan=False, strict=True)]
Cost = Annotated[FiniteNumber, Field(ge=0)]
Effect = Annotated[FiniteNumber, Field(ge=-1, le=1)]
Probability = Annotated[FiniteNumber, Field(ge=0, le=1)]


class ArtifactReferences(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    artifact_paths: dict[str, str]
    artifact_hashes: dict[str, str] = Field(default_factory=dict)

    @field_validator("artifact_paths")
    @classmethod
    def _contained_names(cls, paths: dict[str, str]) -> dict[str, str]:
        if any(ARTIFACT_FILES.get(key) != value for key, value in paths.items()):
            raise ValueError("artifact_paths must name recognized files inside the audit directory")
        return paths

    @field_validator("artifact_hashes")
    @classmethod
    def _sha256_values(cls, hashes: dict[str, str]) -> dict[str, str]:
        for key, value in hashes.items():
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"artifact_hashes.{key} must be a lowercase SHA-256 digest")
        return hashes


class VerdictExplanationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    verdict: Verdict
    first_matching_branch: str
    conditions: dict[str, bool | float | None]
    suppressed_branches: list[str]
    summary: str


class ClaimSummary(ArtifactReferences):
    model_config = ConfigDict(extra="forbid")

    study_id: str
    claim_id: str
    claim_text: str
    treatment: str
    control: str
    verdict: Verdict
    claim_status: Literal["supported", "unsupported", "inconclusive"]
    readiness: ReadinessStatus
    delta: Effect
    ci_low: Effect
    ci_high: Effect
    adjusted_p_value: Probability | None
    rejects_null: bool
    paired_tasks: int = Field(gt=0, strict=True)
    cost_provenance: Literal[
        "reconciled", "as_reported_only", "partial", "cost_not_available", "mixed", "n/a"
    ]
    treatment_total_cost_usd: Cost | None
    control_total_cost_usd: Cost | None
    cost_caveat: str
    verdict_explanation: VerdictExplanationPayload
    human_summary: str

    @model_validator(mode="after")
    def _consistent_claim(self) -> ClaimSummary:
        if self.ci_low > self.ci_high:
            raise ValueError("ci_low must not exceed ci_high")
        if self.verdict != self.verdict_explanation.verdict:
            raise ValueError("verdict must match verdict_explanation.verdict")
        if self.treatment == self.control:
            raise ValueError("treatment and control must differ")
        if self.cost_provenance == "cost_not_available" and (
            self.treatment_total_cost_usd is not None or self.control_total_cost_usd is not None
        ):
            raise ValueError("cost_not_available requires null claim costs")
        for name in ("study_id", "claim_id", "treatment", "control"):
            if not getattr(self, name):
                raise ValueError(f"{name} must be nonempty")
        return self


class AuditSummary(ArtifactReferences):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    study_id: str
    readiness: ReadinessStatus
    claims: list[ClaimSummary] = Field(min_length=1)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def _consistent_audit(self) -> AuditSummary:
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError("claim IDs must be unique")
        for claim in self.claims:
            if claim.study_id != self.study_id or claim.readiness != self.readiness:
                raise ValueError(
                    f"claim {claim.claim_id!r} must match audit study_id and readiness"
                )
            if (
                claim.artifact_paths != self.artifact_paths
                or claim.artifact_hashes != self.artifact_hashes
            ):
                raise ValueError(f"claim {claim.claim_id!r} must reference the audit artifacts")
        return self

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
