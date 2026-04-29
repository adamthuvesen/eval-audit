"""Ingest adapters that produce canonical RunRecord frames."""

from rigor.ingest.base import IngestAdapter, IngestContractError, assert_canonical_schema
from rigor.ingest.hal_gaia import HalGaiaAdapter
from rigor.ingest.hal_tau_bench import HalTauBenchAdapter
from rigor.ingest.synthetic import SyntheticAdapter

__all__ = [
    "HalGaiaAdapter",
    "HalTauBenchAdapter",
    "IngestAdapter",
    "IngestContractError",
    "SyntheticAdapter",
    "assert_canonical_schema",
]
