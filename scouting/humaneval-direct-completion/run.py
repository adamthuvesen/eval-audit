"""HumanEval Direct Completion harness — `eval-audit/humaneval-direct-completion-v1`.

Calls the Anthropic Messages API once per (model, task, run) and writes the
raw response to ``scouting/humaneval-direct-completion/raw/<agent_short>/<task_id>/<run_id>.json``.

The harness is intentionally thin: stdlib only, no agent framework, no tools.
Reproducibility lever: temperature=0. The 2 reruns capture provider-level
non-determinism. See ``run-plan.md`` for the locked design.

Usage:

    uv run python scouting/humaneval-direct-completion/run.py

Env: reads ``ANTHROPIC_API_KEY`` from ``.env.local`` (or the ambient
environment). The script is a no-op if all 120 raw outputs already exist —
re-running it does not overwrite files; delete a raw/ file to force a re-run
of just that (model, task, run).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS_PATH = HERE / "humaneval-tasks-30.jsonl"
RAW_DIR = HERE / "raw"

SYSTEM_PROMPT = (
    "Complete the following Python function. Output only the function body — "
    "no triple backticks, no `def` line, no surrounding prose."
)

MODELS = [
    {
        "agent_id": "humaneval-direct-haiku-4-5",
        "agent_short": "haiku45",
        "model_id": "claude-haiku-4-5-20251001",
    },
    {
        "agent_id": "humaneval-direct-sonnet-4-6",
        "agent_short": "sonnet46",
        "model_id": "claude-sonnet-4-6",
    },
]

RERUNS = 2
TEMPERATURE = 0
MAX_TOKENS = 1024
API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
RETRY_ON_STATUS = {429, 500, 502, 503, 504, 529}
MAX_RETRIES = 4


def _load_env_local() -> None:
    """Best-effort .env.local loader (no python-dotenv dep).

    Overrides empty existing values (some sandboxes set ``ANTHROPIC_API_KEY=``
    with an empty string, which would otherwise survive ``setdefault``).
    """
    env_path = HERE.parent.parent / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not os.environ.get(key):
            os.environ[key] = value


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=HERE,
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _call_api(api_key: str, model_id: str, prompt: str) -> dict:
    body = json.dumps(
        {
            "model": model_id,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )

    delay = 2.0
    last_err: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode())
                return {"ok": True, "payload": payload, "attempts": attempt}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")
            last_err = f"HTTP {exc.code}: {err_body[:500]}"
            if exc.code in RETRY_ON_STATUS and attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            return {"ok": False, "error": last_err, "attempts": attempt}
        except urllib.error.URLError as exc:
            last_err = f"URLError: {exc}"
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            return {"ok": False, "error": last_err, "attempts": attempt}
    return {"ok": False, "error": last_err or "unknown", "attempts": MAX_RETRIES}


def main() -> None:
    _load_env_local()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set; aborting.")

    if not TASKS_PATH.exists():
        raise SystemExit(f"missing tasks file: {TASKS_PATH}")
    tasks = [json.loads(line) for line in TASKS_PATH.read_text().splitlines() if line.strip()]
    assert len(tasks) == 30, len(tasks)

    git_commit = _git_commit()
    total = 0
    skipped = 0
    errors = 0
    for model in MODELS:
        agent_short = model["agent_short"]
        for task in tasks:
            task_id = task["task_id"]
            for run_idx in range(1, RERUNS + 1):
                run_id = f"run-{agent_short}-{run_idx}"
                out_dir = RAW_DIR / agent_short / task_id.replace("/", "_")
                out_path = out_dir / f"{run_id}.json"
                total += 1
                if out_path.exists():
                    skipped += 1
                    continue
                out_dir.mkdir(parents=True, exist_ok=True)
                started = datetime.now(UTC).isoformat()
                t0 = time.monotonic()
                result = _call_api(api_key, model["model_id"], task["prompt"])
                latency_s = time.monotonic() - t0
                ended = datetime.now(UTC).isoformat()
                record = {
                    "agent_id": model["agent_id"],
                    "agent_short": agent_short,
                    "model_id": model["model_id"],
                    "task_id": task_id,
                    "run_id": run_id,
                    "harness": "eval-audit/humaneval-direct-completion-v1",
                    "harness_commit": git_commit,
                    "system_prompt": SYSTEM_PROMPT,
                    "user_prompt": task["prompt"],
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "started_at": started,
                    "ended_at": ended,
                    "latency_s": latency_s,
                    **result,
                }
                out_path.write_text(json.dumps(record, indent=2) + "\n")
                if not result.get("ok"):
                    errors += 1
                    print(f"  ERR  {agent_short} {task_id} {run_id}: {result.get('error')}")
                else:
                    usage = result["payload"].get("usage", {})
                    print(
                        f"  OK   {agent_short} {task_id} {run_id} "
                        f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
                        f"{latency_s:.1f}s"
                    )

    print(f"done: total={total} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    main()
