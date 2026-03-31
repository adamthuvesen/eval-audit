"""Ingest adapters that produce canonical RunRecord frames."""

from rigor.ingest.base import IngestAdapter, IngestContractError, assert_canonical_schema

__all__ = ["IngestAdapter", "IngestContractError", "assert_canonical_schema"]
