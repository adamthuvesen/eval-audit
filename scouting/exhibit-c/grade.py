"""Grade Exhibit C raw outputs by executing HumanEval unit tests in subprocess.

Reads ``scouting/exhibit-c/raw/<agent_short>/<task_id>/<run_id>.json``,
extracts the model's completion, concatenates it with the HumanEval `prompt`
and `test`, and runs the result under a fresh `python` subprocess with a
10-second timeout. No `eval()` happens in the parent process.

Writes ``scouting/exhibit-c/graded/<agent_short>/<task_id>/<run_id>.json``
with grading details. Idempotent: existing graded files are not overwritten.

Trust boundary (v0):
  The grader executes untrusted model-generated code. The sandbox is:
    - sanitized environment (only PATH passed; ANTHROPIC_API_KEY, HOME, and
      other secrets are scrubbed)
    - Python isolated mode (-I): ignores PYTHONPATH, PYTHONHOME, and user
      site-packages, so the candidate cannot import repo-local code
    - 10s timeout
    - temporary cwd
  Stronger isolation (container, network deny, rlimit-based memory cap) is
  out of scope for v0. Do not run this grader on shared infrastructure or
  with secrets present in the environment of the parent process.

Usage:

    uv run python scouting/exhibit-c/grade.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS_PATH = HERE / "humaneval-tasks-30.jsonl"
RAW_DIR = HERE / "raw"
GRADED_DIR = HERE / "graded"

GRADE_TIMEOUT_S = 10
_FENCE_RE = re.compile(r"```(?:python)?\n?(.*?)```", re.DOTALL)


def _extract_completion(payload: dict) -> str:
    """Pull the assistant's text out of an Anthropic Messages API payload."""
    blocks = payload.get("content", [])
    text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    raw = "\n".join(text_parts)
    fence = _FENCE_RE.search(raw)
    if fence:
        return fence.group(1)
    return raw


def _candidates(prompt: str, completion: str, test: str, entry_point: str) -> list[str]:
    """Generate candidate runnable programs from prompt + completion.

    The system prompt asks for "function body only", but models comply
    inconsistently and the right wrapping depends on the shape of the
    completion. Generate the plausible wrappings here; the caller picks
    the first one that parses (see ``_build_program``).
    """
    body = completion.rstrip("\n")
    stripped = body.lstrip()
    suffix = "\n" + test + "\n" + f"check({entry_point})\n"

    out: list[str] = []

    # Strategy A: model redefined the function — use the prompt up to the
    # first ``def`` plus the model's full function in place of the prompt's
    # signature.
    if stripped.startswith("def "):
        prompt_head = prompt.partition("def ")[0]
        out.append(prompt_head + body.lstrip() + suffix)

    # Strategy B: indent only the lines that aren't already indented.
    # Right for "first line at col 0, rest at col 4" (common in Haiku).
    lines_b: list[str] = []
    for line in body.split("\n"):
        if not line.strip() or line.startswith((" ", "\t")):
            lines_b.append(line)
        else:
            lines_b.append("    " + line)
    out.append(prompt + "\n".join(lines_b) + suffix)

    # Strategy C: indent every non-empty line by 4 spaces.
    # Right for fully-unindented body that has its own nested 4-space
    # blocks (e.g. unindented `for ...:` over indented loop body).
    lines_c: list[str] = []
    for line in body.split("\n"):
        if not line.strip():
            lines_c.append(line)
        else:
            lines_c.append("    " + line)
    out.append(prompt + "\n".join(lines_c) + suffix)

    # Strategy D: textwrap.dedent then indent uniformly by 4. Handles
    # completions whose base indent is something odd like 3 spaces (some
    # models produce these), preserving relative nesting.
    dedented = textwrap.dedent(body).rstrip("\n")
    lines_d: list[str] = []
    for line in dedented.split("\n"):
        if not line.strip():
            lines_d.append(line)
        else:
            lines_d.append("    " + line)
    out.append(prompt + "\n".join(lines_d) + suffix)

    # Strategy E: floor each non-empty line's leading-space count up to a
    # minimum of 4. Catches "first line at 3 spaces by typo, rest at 4+
    # spaces" — common in some Sonnet outputs — without disturbing already
    # well-indented bodies.
    lines_e: list[str] = []
    for line in body.split("\n"):
        if not line.strip():
            lines_e.append(line)
            continue
        leading = len(line) - len(line.lstrip(" "))
        if leading < 4:
            lines_e.append(" " * (4 - leading) + line)
        else:
            lines_e.append(line)
    out.append(prompt + "\n".join(lines_e) + suffix)

    # Dedup while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for c in out:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _build_program(prompt: str, completion: str, test: str, entry_point: str) -> str:
    """Pick the first wrapping of completion that compiles cleanly.

    Uses ``compile(..., 'exec')`` rather than ``ast.parse`` because the latter
    does not catch ``return`` at module scope (a real failure mode here when
    a helper-def-plus-bare-return completion is concatenated naively).

    Falls back to the first candidate if none compile — the subprocess will
    then surface the error honestly in stderr.
    """
    cands = _candidates(prompt, completion, test, entry_point)
    for c in cands:
        try:
            compile(c, "<exhibit-c>", "exec")
            return c
        except (SyntaxError, ValueError):
            continue
    return cands[0]


def _sandboxed_env() -> dict[str, str]:
    """Return the sanitized env passed to the grader subprocess.

    Only ``PATH`` is forwarded from the parent. ``ANTHROPIC_API_KEY``, ``HOME``,
    repo-relative ``PYTHONPATH``, and other secrets are intentionally absent
    so a malicious or accidental completion cannot read them. ``PATH`` is
    needed to resolve the Python interpreter itself on some platforms.
    """
    return {"PATH": os.environ.get("PATH", "")}


def _grade_one(prompt: str, completion: str, test: str, entry_point: str) -> dict:
    """Run prompt + completion + test in a subprocess. Return grade dict.

    Sandbox (see module docstring): sanitized env, Python isolated mode (-I),
    10s timeout, temporary cwd. The candidate program runs against an
    interpreter that has no access to PYTHONPATH, user site-packages, or the
    parent's environment variables.
    """
    program = _build_program(prompt, completion, test, entry_point)
    with tempfile.TemporaryDirectory(prefix="exhibit-c-grade-") as tmp:
        path = Path(tmp) / "candidate.py"
        path.write_text(program)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(path)],
                capture_output=True,
                timeout=GRADE_TIMEOUT_S,
                cwd=tmp,
                env=_sandboxed_env(),
            )
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stderr_tail": proc.stderr.decode(errors="replace")[-500:],
                "timeout": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": None,
                "stderr_tail": "TIMEOUT",
                "timeout": True,
            }
        except Exception as exc:
            return {
                "success": False,
                "returncode": None,
                "stderr_tail": f"GRADER_CRASH: {type(exc).__name__}: {exc}",
                "timeout": False,
            }


def main() -> None:
    if not TASKS_PATH.exists():
        raise SystemExit(f"missing tasks file: {TASKS_PATH}")
    tasks = {
        json.loads(line)["task_id"]: json.loads(line)
        for line in TASKS_PATH.read_text().splitlines()
        if line.strip()
    }
    assert len(tasks) == 30, len(tasks)

    raw_files = sorted(RAW_DIR.rglob("*.json"))
    if not raw_files:
        raise SystemExit(f"no raw outputs under {RAW_DIR}; run run.py first.")

    total = 0
    skipped = 0
    n_pass = 0
    n_fail = 0
    n_errored = 0
    for raw_path in raw_files:
        rel = raw_path.relative_to(RAW_DIR)
        graded_path = GRADED_DIR / rel
        if graded_path.exists():
            skipped += 1
            total += 1
            continue
        record = json.loads(raw_path.read_text())
        task_id = record["task_id"]
        if task_id not in tasks:
            raise SystemExit(f"unknown task_id in {raw_path}: {task_id}")
        task = tasks[task_id]

        graded: dict
        if not record.get("ok"):
            graded = {
                "outcome_status": "errored",
                "success": None,
                "completion": None,
                "grader": {"reason": "api_error", "detail": record.get("error", "")[:500]},
            }
            n_errored += 1
        else:
            completion = _extract_completion(record["payload"])
            grade = _grade_one(
                prompt=task["prompt"],
                completion=completion,
                test=task["test"],
                entry_point=task["entry_point"],
            )
            graded = {
                "outcome_status": "graded",
                "success": grade["success"],
                "completion": completion,
                "grader": grade,
            }
            if grade["success"]:
                n_pass += 1
            else:
                n_fail += 1

        graded_path.parent.mkdir(parents=True, exist_ok=True)
        graded_path.write_text(json.dumps({**record, **graded}, indent=2) + "\n")
        total += 1
        marker = (
            "PASS" if graded.get("success")
            else "FAIL" if graded.get("outcome_status") == "graded"
            else "ERR"
        )
        print(f"  {marker:4s} {record['agent_short']} {task_id} {record['run_id']}")

    print(
        f"done: total={total} skipped={skipped} pass={n_pass} fail={n_fail} errored={n_errored}"
    )


if __name__ == "__main__":
    main()
