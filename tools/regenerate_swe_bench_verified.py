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

    uv run --locked python tools/regenerate_swe_bench_verified.py --cache-dir .scout-cache/swe-pinned
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import polars as pl

from eval_audit.ingest.swe_bench_verified import (
    SWE_BENCH_VERIFIED_TASK_COUNT,
    SweBenchVerifiedAdapter,
    build_canonical_frame,
)
from tools.fixture_io import (
    FixtureSources,
    check_refresh_destination,
    immutable_revision,
    promote_fixture,
    regeneration_parser,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "examples" / "swe-bench-verified-openhands"

VERIFIED_PARQUET_URL = (
    "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/{revision}/"
    "data/test-00000-of-00001.parquet"
)
RESULTS_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/swe-bench/experiments/{commit}/"
    "evaluation/verified/{submission}/results/results.json"
)

TREATMENT_DIR = "20251127_openhands_claude-opus-4-5"
CONTROL_DIR = "20250807_openhands_gpt5"

TREATMENT_MODEL_ID = "claude-opus-4-5-202511017"
CONTROL_MODEL_ID = "gpt-5-2025-08-07"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_task_universe(parquet_bytes: bytes) -> list[str]:
    frame = pl.read_parquet(io.BytesIO(parquet_bytes))
    if "instance_id" not in frame.columns:
        raise RuntimeError("SWE-bench Verified parquet is missing 'instance_id' column")
    universe = frame["instance_id"].to_list()
    if any(not isinstance(task, str) or not task for task in universe):
        raise ValueError("Verified parquet instance_ids must be non-empty strings")
    if len(universe) != SWE_BENCH_VERIFIED_TASK_COUNT:
        raise RuntimeError(
            f"Expected {SWE_BENCH_VERIFIED_TASK_COUNT} Verified tasks; got {len(universe)}"
        )
    if len(set(universe)) != len(universe):
        raise RuntimeError("Verified parquet contains duplicate instance_ids")
    return sorted(universe)


def _load_results_json(sources: FixtureSources, commit: str, submission: str) -> tuple[bytes, dict]:
    url = RESULTS_URL_TEMPLATE.format(commit=commit, submission=submission)
    raw = sources.read(url)
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict) or "resolved" not in parsed:
        raise ValueError(f"{submission}: expected a results object with resolved task IDs")
    for field in ("resolved", "no_generation", "no_logs"):
        values = parsed.get(field, [])
        if not isinstance(values, list) or any(
            not isinstance(task, str) or not task for task in values
        ):
            raise ValueError(f"{submission}: {field} must be a list of non-empty task IDs")
        if len(values) != len(set(values)):
            raise ValueError(f"{submission}: duplicate task IDs in {field}")
    return raw, parsed


def main() -> None:
    parser = regeneration_parser(__doc__ or "Regenerate fixture", FIXTURE_DIR)
    parser.add_argument("--experiments-revision", type=immutable_revision)
    args = parser.parse_args()
    check_refresh_destination(args.mode, args.output_dir, args.accept_evidence_change)
    revisions = {}
    if args.mode == "refresh":
        if not args.revision or not args.experiments_revision:
            parser.error("refresh requires --revision and --experiments-revision")
        revisions = {"dataset": args.revision, "experiments": args.experiments_revision}
    elif args.revision or args.experiments_revision:
        parser.error("replay uses revisions from the cache manifest")
    sources = FixtureSources(args.cache_dir, mode=args.mode, revisions=revisions)
    pinned_commit = sources.manifest.revisions["experiments"]
    verified_url = VERIFIED_PARQUET_URL.format(revision=sources.manifest.revisions["dataset"])
    verified_bytes = sources.read(verified_url)
    universe = _load_task_universe(verified_bytes)
    print(f"  loaded {len(universe)} instance_ids")

    print(f"Reading {TREATMENT_DIR}/results.json ...")
    treat_raw, treat_parsed = _load_results_json(sources, pinned_commit, TREATMENT_DIR)
    print(f"  resolved={len(treat_parsed['resolved'])}")
    print(f"Reading {CONTROL_DIR}/results.json ...")
    ctrl_raw, ctrl_parsed = _load_results_json(sources, pinned_commit, CONTROL_DIR)
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
    treat_succ = int(frame.filter(pl.col("agent_id") == TREATMENT_DIR)["success"].sum())
    ctrl_succ = int(frame.filter(pl.col("agent_id") == CONTROL_DIR)["success"].sum())
    print(f"  treatment success count: {treat_succ}/{SWE_BENCH_VERIFIED_TASK_COUNT}")
    print(f"  control success count:   {ctrl_succ}/{SWE_BENCH_VERIFIED_TASK_COUNT}")

    provenance = {
        "scouting_decision": "scouting/swe-bench-verified-openhands-decision.md",
        "swe_bench_experiments_commit": pinned_commit,
        "dataset_revision": sources.manifest.revisions["dataset"],
        "fetched_at_utc": sources.manifest.recorded_at,
        "sources": [
            {
                "url": verified_url,
                "sha256": _sha256(verified_bytes),
                "purpose": "SWE-bench Verified 500-task universe",
            },
            {
                "url": RESULTS_URL_TEMPLATE.format(commit=pinned_commit, submission=TREATMENT_DIR),
                "sha256": _sha256(treat_raw),
                "purpose": "treatment submission resolved/no_generation/no_logs",
            },
            {
                "url": RESULTS_URL_TEMPLATE.format(commit=pinned_commit, submission=CONTROL_DIR),
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
    SweBenchVerifiedAdapter().validate(frame)
    sources.save_manifest()
    promote_fixture(
        frame,
        provenance,
        args.output_dir,
        SweBenchVerifiedAdapter().load,
        accept_evidence_change=args.accept_evidence_change,
    )
    print(f"Wrote validated fixture to {args.output_dir}")


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        RuntimeError,
        OSError,
        KeyError,
        TypeError,
        pl.exceptions.PolarsError,
    ) as exc:
        import sys

        print(f"fixture regeneration failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
