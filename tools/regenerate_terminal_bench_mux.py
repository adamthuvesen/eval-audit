"""Regenerate the Terminal-Bench 2.0 Mux committed fixture.

Reads public Terminal-Bench 2.0 leaderboard artifacts from:

- https://www.tbench.ai/leaderboard/terminal-bench/2.0
- https://huggingface.co/datasets/harborframework/terminal-bench-2-leaderboard

Writes:

- ``examples/terminal-bench-2-mux/runs.parquet``
- ``examples/terminal-bench-2-mux/provenance.json``

Usage:

    uv run --locked python tools/regenerate_terminal_bench_mux.py --cache-dir .scout-cache/terminal-pinned
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from datetime import datetime
from pathlib import Path

import polars as pl
import yaml

from eval_audit.ingest.terminal_bench import (
    TERMINAL_BENCH_2_TASK_COUNT,
    TerminalBenchMuxAdapter,
    build_canonical_frame,
)
from tools.fixture_io import (
    FixtureSources,
    check_refresh_destination,
    promote_fixture,
    regeneration_parser,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "examples" / "terminal-bench-2-mux"

DATASET_ID = "harborframework/terminal-bench-2-leaderboard"
DATASET_ROOT_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
LEADERBOARD_URL = "https://www.tbench.ai/leaderboard/terminal-bench/2.0"
SUBMISSION_ROOT = "submissions/terminal-bench/2.0"

SUBMISSIONS = {
    "Mux__GPT-5.3-Codex": {
        "role": "treatment",
        "official_accuracy": "74.6%",
        "official_accuracy_ci": "±2.5",
    },
    "Mux__Claude-Opus-4.6": {
        "role": "control",
        "official_accuracy": "66.5%",
        "official_accuracy_ci": "±2.5",
    },
}


def _api_tree(sources: FixtureSources, path: str) -> list[dict]:
    quoted = urllib.parse.quote(path, safe="/")
    url = f"https://huggingface.co/api/datasets/{DATASET_ID}/tree/{sources.manifest.revisions['dataset']}/{quoted}?limit=1000"
    items = json.loads(sources.read(url))
    if not isinstance(items, list) or len(items) >= 1000:
        raise ValueError("invalid or paginated dataset tree response")
    return items


def _resolve_url(sources: FixtureSources, path: str) -> str:
    quoted = urllib.parse.quote(path, safe="/")
    return f"{DATASET_ROOT_URL}/resolve/{sources.manifest.revisions['dataset']}/{quoted}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _submission_path(submission: str) -> str:
    return f"{SUBMISSION_ROOT}/{submission}"


def _metadata(sources: FixtureSources, submission: str) -> tuple[dict, bytes]:
    path = f"{_submission_path(submission)}/metadata.yaml"
    raw = sources.read(_resolve_url(sources, path))
    return yaml.safe_load(raw.decode("utf-8")), raw


def _job_dirs(sources: FixtureSources, submission: str) -> list[str]:
    items = _api_tree(sources, _submission_path(submission))
    return sorted(item["path"].split("/")[-1] for item in items if item["type"] == "directory")


def _task_trial_dirs(sources: FixtureSources, submission: str, run_id: str) -> list[str]:
    items = _api_tree(sources, f"{_submission_path(submission)}/{run_id}")
    task_dirs = sorted(item["path"].split("/")[-1] for item in items if item["type"] == "directory")
    if len(task_dirs) != TERMINAL_BENCH_2_TASK_COUNT:
        raise RuntimeError(
            f"{submission}/{run_id} expected {TERMINAL_BENCH_2_TASK_COUNT} "
            f"task trials, got {len(task_dirs)}"
        )
    return task_dirs


def _result(
    sources: FixtureSources, submission: str, run_id: str, trial_dir: str
) -> tuple[dict, bytes]:
    rel_path = f"{_submission_path(submission)}/{run_id}/{trial_dir}/result.json"
    raw = sources.read(_resolve_url(sources, rel_path))
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{rel_path}: expected a result object")
    usage = parsed.get("agent_result")
    if not isinstance(usage, dict):
        raise ValueError(f"{rel_path}: missing agent_result usage")
    for field in ("n_input_tokens", "n_output_tokens"):
        if type(usage.get(field)) is not int or usage[field] < 0:
            raise ValueError(f"{rel_path}: {field} must be an explicit non-negative integer")
    timestamps = []
    for field in ("started_at", "finished_at"):
        value = parsed.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{rel_path}: missing {field} timestamp")
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError(f"{rel_path}: {field} must include a timezone")
        timestamps.append(timestamp)
    if timestamps[1] < timestamps[0]:
        raise ValueError(f"{rel_path}: finished_at precedes started_at")
    parsed["_submission_path"] = rel_path
    return parsed, raw


def _load_submission(sources: FixtureSources, submission: str) -> tuple[dict, dict]:
    metadata, metadata_raw = _metadata(sources, submission)
    runs: dict[str, list[dict]] = {}
    manifest_hash = hashlib.sha256()
    manifest_hash.update(metadata_raw)
    result_count = 0

    for run_id in _job_dirs(sources, submission):
        task_dirs = _task_trial_dirs(sources, submission, run_id)

        fetched = [_result(sources, submission, run_id, trial_dir) for trial_dir in task_dirs]
        runs[run_id] = [parsed for parsed, _raw in fetched]
        for _parsed, raw in fetched:
            manifest_hash.update(raw)
        result_count += len(fetched)

    provenance = {
        "metadata_sha256": _sha256(metadata_raw),
        "result_json_count": result_count,
        "result_manifest_sha256": manifest_hash.hexdigest(),
        "run_ids": sorted(runs),
        "task_count_per_run": TERMINAL_BENCH_2_TASK_COUNT,
    }
    return {"metadata": metadata, "runs": runs}, provenance


def main() -> None:
    parser = regeneration_parser(__doc__ or "Regenerate fixture", FIXTURE_DIR)
    args = parser.parse_args()
    check_refresh_destination(args.mode, args.output_dir, args.accept_evidence_change)
    if args.mode == "refresh" and not args.revision:
        parser.error("refresh requires --revision")
    if args.mode == "replay" and args.revision:
        parser.error("replay uses the revision from the cache manifest")
    sources = FixtureSources(
        args.cache_dir,
        mode=args.mode,
        revisions={"dataset": args.revision} if args.mode == "refresh" else {},
    )
    fetched_at = sources.manifest.recorded_at
    submissions: dict[str, dict] = {}
    submission_provenance: dict[str, dict] = {}

    print(f"Reading Terminal-Bench 2.0 Mux sources ({args.mode})...")
    for submission in SUBMISSIONS:
        print(f"  {submission}")
        parsed, provenance = _load_submission(sources, submission)
        submissions[submission] = parsed
        submission_provenance[submission] = provenance
        print(f"    runs={len(parsed['runs'])}, result_json={provenance['result_json_count']}")

    print("Building canonical RunRecord frame...")
    frame = build_canonical_frame(submissions=submissions)
    for submission in SUBMISSIONS:
        success_count = int(frame.filter(pl.col("agent_id") == submission)["success"].sum())
        submission_rows = frame.filter(pl.col("agent_id") == submission).height
        print(f"  {submission}: {success_count}/{submission_rows}")

    provenance = {
        "scouting_decision": "scouting/terminal-bench-2-mux-decision.md",
        "fetched_at_utc": fetched_at,
        "dataset_revision": sources.manifest.revisions["dataset"],
        "retrieved_at": fetched_at,
        "source_url": LEADERBOARD_URL,
        "sources": [
            {
                "url": LEADERBOARD_URL,
                "purpose": "Terminal-Bench 2.0 official leaderboard rows",
            },
            {
                "url": DATASET_ROOT_URL,
                "purpose": "Terminal-Bench 2.0 public leaderboard result.json artifacts",
            },
        ],
        "agents": {
            submission: {
                **SUBMISSIONS[submission],
                **submission_provenance[submission],
                "metadata_url": _resolve_url(
                    sources, f"{_submission_path(submission)}/metadata.yaml"
                ),
            }
            for submission in SUBMISSIONS
        },
        "task_universe": {
            "task_count": TERMINAL_BENCH_2_TASK_COUNT,
            "runs_per_agent": 5,
            "task_key": "task_name",
        },
        "cost_provenance": "cost_not_available",
        "cost_provenance_reason": (
            "The selected public result.json artifacts expose token counts but "
            "agent_result.cost_usd is incomplete across the selected "
            "submissions. The fixture keeps canonical cost fields null and "
            "suppresses cost-derived report views."
        ),
    }
    sources.save_manifest()
    promote_fixture(
        frame,
        provenance,
        args.output_dir,
        TerminalBenchMuxAdapter().load,
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
        yaml.YAMLError,
        pl.exceptions.PolarsError,
    ) as exc:
        import sys

        print(f"fixture regeneration failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
