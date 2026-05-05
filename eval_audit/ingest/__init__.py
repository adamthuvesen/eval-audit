"""Ingest adapters that produce canonical RunRecord frames."""

from eval_audit.ingest.base import (
    IngestAdapter,
    IngestContractError,
    assert_canonical_schema,
    validate_run_records,
)
from eval_audit.ingest.generic import load_run_records
from eval_audit.ingest.hal_gaia import HalGaiaAdapter
from eval_audit.ingest.hal_tau_bench import HalTauBenchAdapter
from eval_audit.ingest.swe_bench_verified import SweBenchVerifiedAdapter
from eval_audit.ingest.synthetic import SyntheticAdapter

__all__ = [
    "HalGaiaAdapter",
    "HalTauBenchAdapter",
    "IngestAdapter",
    "IngestContractError",
    "SweBenchVerifiedAdapter",
    "SyntheticAdapter",
    "assert_canonical_schema",
    "load_run_records",
    "validate_run_records",
]
