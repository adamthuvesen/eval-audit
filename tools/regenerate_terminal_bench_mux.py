"""Regenerate the Terminal-Bench 2.0 Mux committed fixture.

Reads public Terminal-Bench 2.0 leaderboard artifacts from:

- https://www.tbench.ai/leaderboard/terminal-bench/2.0
- https://huggingface.co/datasets/harborframework/terminal-bench-2-leaderboard

Writes:

- ``examples/terminal-bench-2-mux/runs.parquet``
- ``examples/terminal-bench-2-mux/provenance.json``

Usage:

    uv run python tools/regenerate_terminal_bench_mux.py
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import yaml

from eval_audit.ingest.terminal_bench import (
    TERMINAL_BENCH_2_TASK_COUNT,
    TerminalBenchMuxAdapter,
    build_canonical_frame,
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


def _api_tree(path: str) -> list[dict]:
    quoted = urllib.parse.quote(path, safe="/")
    url = f"https://huggingface.co/api/datasets/{DATASET_ID}/tree/main/{quoted}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _resolve_url(path: str) -> str:
    quoted = urllib.parse.quote(path, safe="/")
    return f"{DATASET_ROOT_URL}/resolve/main/{quoted}"


def _fetch(url: str) -> bytes:
    last_error: urllib.error.HTTPError | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == 4:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 2.0 * (attempt + 1)
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _submission_path(submission: str) -> str:
    return f"{SUBMISSION_ROOT}/{submission}"


def _metadata(submission: str) -> tuple[dict, bytes]:
    path = f"{_submission_path(submission)}/metadata.yaml"
    raw = _fetch(_resolve_url(path))
    return yaml.safe_load(raw.decode("utf-8")), raw


def _job_dirs(submission: str) -> list[str]:
    items = _api_tree(_submission_path(submission))
    return sorted(item["path"].split("/")[-1] for item in items if item["type"] == "directory")


def _task_trial_dirs(submission: str, run_id: str) -> list[str]:
    items = _api_tree(f"{_submission_path(submission)}/{run_id}")
    task_dirs = sorted(item["path"].split("/")[-1] for item in items if item["type"] == "directory")
    if len(task_dirs) != TERMINAL_BENCH_2_TASK_COUNT:
        raise RuntimeError(
            f"{submission}/{run_id} expected {TERMINAL_BENCH_2_TASK_COUNT} "
            f"task trials, got {len(task_dirs)}"
        )
    return task_dirs


def _result(submission: str, run_id: str, trial_dir: str) -> tuple[dict, bytes]:
    rel_path = f"{_submission_path(submission)}/{run_id}/{trial_dir}/result.json"
    raw = _fetch(_resolve_url(rel_path))
    parsed = json.loads(raw.decode("utf-8"))
    parsed["_submission_path"] = rel_path
    return parsed, raw


def _load_submission(submission: str) -> tuple[dict, dict]:
    metadata, metadata_raw = _metadata(submission)
    runs: dict[str, list[dict]] = {}
    manifest_hash = hashlib.sha256()
    manifest_hash.update(metadata_raw)
    result_count = 0

    for run_id in _job_dirs(submission):
        task_dirs = _task_trial_dirs(submission, run_id)

        def fetch_trial(trial_dir: str, run_id: str = run_id) -> tuple[dict, bytes]:
            return _result(submission, run_id, trial_dir)

        with ThreadPoolExecutor(max_workers=4) as executor:
            fetched = list(executor.map(fetch_trial, task_dirs))
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
    fetched_at = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    submissions: dict[str, dict] = {}
    submission_provenance: dict[str, dict] = {}

    print("Fetching Terminal-Bench 2.0 Mux submissions from Hugging Face...")
    for submission in SUBMISSIONS:
        print(f"  {submission}")
        parsed, provenance = _load_submission(submission)
        submissions[submission] = parsed
        submission_provenance[submission] = provenance
        print(f"    runs={len(parsed['runs'])}, result_json={provenance['result_json_count']}")

    print("Building canonical RunRecord frame...")
    frame = build_canonical_frame(submissions=submissions)
    for submission in SUBMISSIONS:
        success_count = int(frame.filter(pl.col("agent_id") == submission)["success"].sum())
        submission_rows = frame.filter(pl.col("agent_id") == submission).height
        print(f"  {submission}: {success_count}/{submission_rows}")

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    runs_path = FIXTURE_DIR / "runs.parquet"
    frame.write_parquet(runs_path)
    print(f"Wrote {runs_path} ({frame.height} rows)")

    provenance = {
        "scouting_decision": "scouting/terminal-bench-2-mux-decision.md",
        "fetched_at_utc": fetched_at,
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
                "metadata_url": _resolve_url(f"{_submission_path(submission)}/metadata.yaml"),
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
    provenance_path = FIXTURE_DIR / "provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    TerminalBenchMuxAdapter().load(FIXTURE_DIR)
    print(f"Wrote {provenance_path}")


if __name__ == "__main__":
    main()
