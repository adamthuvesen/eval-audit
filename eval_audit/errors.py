"""Shared input errors for evidence preparation and analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eval_audit.evidence_types import EvidenceCheck


class AnalysisInputError(RuntimeError):
    """Raised when study evidence fails structural preconditions for analysis."""

    def __init__(self, message: str, *, diagnostics: tuple[EvidenceCheck, ...] = ()) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class CrossHarnessComparisonError(AnalysisInputError):
    """Raised when a claim compares treatment and control across harnesses."""


class UnsupportedOutcomeError(AnalysisInputError, ValueError):
    """Raised when an outcome declaration exceeds supported analysis semantics."""


class CostProvenanceError(AnalysisInputError, ValueError):
    """Raised when cost provenance cannot support decision reporting."""
