"""Enumerations shared by schema, ingest, and stats layers."""

from __future__ import annotations

from enum import StrEnum


class CostProvenance(StrEnum):
    """Provenance class for cost data, inherited verbatim from scouting."""

    RECONCILED = "reconciled"
    PARTIAL = "partial"
    AS_REPORTED_ONLY = "as_reported_only"


class OutcomeStatus(StrEnum):
    """Whether a task was graded normally or errored upstream."""

    GRADED = "graded"
    ERRORED = "errored"
