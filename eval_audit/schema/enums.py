"""Enumerations shared by schema, ingest, and stats layers."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class CostProvenance(StrEnum):
    """Provenance class for cost data, inherited verbatim from scouting."""

    RECONCILED = "reconciled"
    PARTIAL = "partial"
    AS_REPORTED_ONLY = "as_reported_only"
    COST_NOT_AVAILABLE = "cost_not_available"


class OutcomeStatus(StrEnum):
    """Whether a task was graded normally or errored upstream."""

    GRADED = "graded"
    ERRORED = "errored"


Verdict = Literal[
    "switch",
    "hold",
    "drop_from_shortlist",
    "rerun_more_n",
    "hedge_on_cost",
    "inconclusive_no_action",
]
ReadinessStatus = Literal["ready", "ready_with_warnings", "not_ready"]
