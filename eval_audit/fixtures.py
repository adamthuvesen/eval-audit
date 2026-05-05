"""Helpers for locating committed scouting fixtures."""

from __future__ import annotations

_BENCHMARK_DIR_OVERRIDE = {"tau_bench": "tau-bench"}


def benchmark_dir_name(benchmark: str) -> str:
    return _BENCHMARK_DIR_OVERRIDE.get(benchmark, benchmark)
