"""Regenerate the SWE-bench Verified OpenHands committed fixture.

Reads:

- The SWE-bench Verified test split parquet from Hugging Face (500 rows).
- Each submission's `results/results.json` from the `swe-bench/experiments`
  GitHub repo (treatment + control).

Writes:

- `examples/swe-bench-verified-openhands/runs.parquet`
- `examples/swe-bench-verified-openhands/provenance.json`

Determinism contract: re-running this script against the same upstream
content produces a byte-identical `runs.parquet`. Dict iteration order in
the canonical frame is preserved by iterating the task universe (a sorted
list of instance_ids) in a deterministic order.

Usage:

    uv run python tools/regenerate_swe_bench_verified.py
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from eval_audit.ingest.swe_bench_verified import (
    SWE_BENCH_VERIFIED_TASK_COUNT,
    build_canonical_frame,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "examples" / "swe-bench-verified-openhands"

VERIFIED_PARQUET_URL = (
    "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/main/"
    "data/test-00000-of-00001.parquet"
)
EXPERIMENTS_REPO_API = (
    "https://api.github.com/repos/swe-bench/experiments/commits/main"
)
RESULTS_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/swe-bench/experiments/{commit}/"
    "evaluation/verified/{submission}/results/results.json"
)

TREATMENT_DIR = "20251127_openhands_claude-opus-4-5"
CONTROL_DIR = "20250807_openhands_gpt5"

TREATMENT_MODEL_ID = "claude-opus-4-5-202511017"
CONTROL_MODEL_ID = "gpt-5-2025-08-07"


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_task_universe(parquet_bytes: bytes) -> list[str]:
    frame = pl.read_parquet(io.BytesIO(parquet_bytes))
    if "instance_id" not in frame.columns:
        raise RuntimeError(
            "SWE-bench Verified parquet is missing 'instance_id' column"
        )
    universe = frame["instance_id"].to_list()
    if len(universe) != SWE_BENCH_VERIFIED_TASK_COUNT:
        raise RuntimeError(
            f"Expected {SWE_BENCH_VERIFIED_TASK_COUNT} Verified tasks; "
            f"got {len(universe)}"
        )
    if len(set(universe)) != len(universe):
        raise RuntimeError("Verified parquet contains duplicate instance_ids")
    return sorted(universe)


def _load_results_json(commit: str, submission: str) -> tuple[bytes, dict]:
    url = RESULTS_URL_TEMPLATE.format(commit=commit, submission=submission)
    raw = _fetch(url)
    parsed = json.loads(raw.decode("utf-8"))
    return raw, parsed


def main() -> None:
    print("Resolving swe-bench/experiments main commit...")
    api = json.loads(_fetch(EXPERIMENTS_REPO_API).decode("utf-8"))
    pinned_commit = api["sha"]
    print(f"  pinned_commit={pinned_commit}")

    print(f"Fetching SWE-bench Verified test split parquet ({VERIFIED_PARQUET_URL})...")
    verified_bytes = _fetch(VERIFIED_PARQUET_URL)
    universe = _load_task_universe(verified_bytes)
    print(f"  loaded {len(universe)} instance_ids")

    print(f"Fetching {TREATMENT_DIR}/results.json ...")
    treat_raw, treat_parsed = _load_results_json(pinned_commit, TREATMENT_DIR)
    print(f"  resolved={len(treat_parsed['resolved'])}")
    print(f"Fetching {CONTROL_DIR}/results.json ...")
    ctrl_raw, ctrl_parsed = _load_results_json(pinned_commit, CONTROL_DIR)
    print(f"  resolved={len(ctrl_parsed['resolved'])}")

    submissions = {
        TREATMENT_DIR: {
            "model_id": TREATMENT_MODEL_ID,
            "submission_dir": TREATMENT_DIR,
            "resolved": set(treat_parsed["resolved"]),
            "no_generation": set(treat_parsed.get("no_generation", [])),
            "no_logs": set(treat_parsed.get("no_logs", [])),
        },
        CONTROL_DIR: {
            "model_id": CONTROL_MODEL_ID,
            "submission_dir": CONTROL_DIR,
            "resolved": set(ctrl_parsed["resolved"]),
            "no_generation": set(ctrl_parsed.get("no_generation", [])),
            "no_logs": set(ctrl_parsed.get("no_logs", [])),
        },
    }

    print("Building canonical RunRecord frame...")
    frame = build_canonical_frame(task_universe=universe, submissions=submissions)
    treat_succ = int(
        frame.filter(pl.col("agent_id") == TREATMENT_DIR)["success"].sum()
    )
    ctrl_succ = int(
        frame.filter(pl.col("agent_id") == CONTROL_DIR)["success"].sum()
    )
    print(f"  treatment success count: {treat_succ}/{SWE_BENCH_VERIFIED_TASK_COUNT}")
    print(f"  control success count:   {ctrl_succ}/{SWE_BENCH_VERIFIED_TASK_COUNT}")

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    runs_path = FIXTURE_DIR / "runs.parquet"
    frame.write_parquet(runs_path)
    print(f"Wrote {runs_path} ({frame.height} rows)")

    provenance = {
        "scouting_decision": "scouting/swe-bench-verified-openhands-decision.md",
        "swe_bench_experiments_commit": pinned_commit,
        "fetched_at_utc": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [
            {
                "url": VERIFIED_PARQUET_URL,
                "sha256": _sha256(verified_bytes),
                "purpose": "SWE-bench Verified 500-task universe",
            },
            {
                "url": RESULTS_URL_TEMPLATE.format(
                    commit=pinned_commit, submission=TREATMENT_DIR
                ),
                "sha256": _sha256(treat_raw),
                "purpose": "treatment submission resolved/no_generation/no_logs",
            },
            {
                "url": RESULTS_URL_TEMPLATE.format(
                    commit=pinned_commit, submission=CONTROL_DIR
                ),
                "sha256": _sha256(ctrl_raw),
                "purpose": "control submission resolved/no_generation/no_logs",
            },
        ],
        "agents": {
            TREATMENT_DIR: {
                "model_id": TREATMENT_MODEL_ID,
                "resolved_count": len(submissions[TREATMENT_DIR]["resolved"]),
                "no_generation_count": len(submissions[TREATMENT_DIR]["no_generation"]),
                "no_logs_count": len(submissions[TREATMENT_DIR]["no_logs"]),
            },
            CONTROL_DIR: {
                "model_id": CONTROL_MODEL_ID,
                "resolved_count": len(submissions[CONTROL_DIR]["resolved"]),
                "no_generation_count": len(submissions[CONTROL_DIR]["no_generation"]),
                "no_logs_count": len(submissions[CONTROL_DIR]["no_logs"]),
            },
        },
        "cost_provenance": "cost_not_available",
        "cost_provenance_reason": (
            "Sampled OpenHands trajectories expose no stable token, usage, or "
            "cost fields. Cost is suppressed across all rows; report rendering "
            "omits cost-derived columns and Pareto views."
        ),
    }
    provenance_path = FIXTURE_DIR / "provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {provenance_path}")


if __name__ == "__main__":
    main()
