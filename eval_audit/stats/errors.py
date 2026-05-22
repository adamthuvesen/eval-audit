"""Analysis-layer exceptions with explicit failure modes."""

from __future__ import annotations


class CrossHarnessComparisonError(RuntimeError):
    """Raised when a claim's treatment and control run under different harnesses."""


class AnalysisInputError(RuntimeError):
    """Raised when loaded runs fail structural preconditions for analysis."""


class UnsupportedOutcomeError(ValueError):
    """Raised when analyze() receives an outcome declaration outside v0 support."""


class CostProvenanceError(ValueError):
    """Raised when cost provenance is too incomplete for decision reporting."""
