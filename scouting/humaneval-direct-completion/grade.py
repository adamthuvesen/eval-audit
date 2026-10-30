"""Historical HumanEval completion formatting and grading helpers.

Host execution of model completions is disabled. Python isolated mode and a
sanitized environment do not restrict filesystem access, network access, or resources.
The CLI refuses execution until an isolated execution backend exists.
The private trusted-fixture helper is only for repository-authored test programs.
Recorded historical grades are preserved and are not revalidated by this tool.
"""

from __future__ import annotations

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
            compile(c, "<humaneval-direct-completion>", "exec")
            return c
        except (SyntaxError, ValueError):
            continue
    return cands[0]


def _trusted_fixture_env() -> dict[str, str]:
    """Reduce inherited environment exposure for trusted test programs, without containment."""
    return {"PATH": os.environ.get("PATH", "")}


def _grade_trusted_fixture(prompt: str, completion: str, test: str, entry_point: str) -> dict:
    """Execute repository-authored fixtures only. This helper provides no containment."""
    program = _build_program(prompt, completion, test, entry_point)
    with tempfile.TemporaryDirectory(prefix="humaneval-direct-completion-grade-") as tmp:
        path = Path(tmp) / "candidate.py"
        receipt = Path(tmp) / "check-completed"
        program += "\nfrom pathlib import Path as _ReceiptPath\n_ReceiptPath('check-completed').write_text('completed')\n"
        path.write_text(program)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(path)],
                capture_output=True,
                timeout=GRADE_TIMEOUT_S,
                cwd=tmp,
                env=_trusted_fixture_env(),
            )
            return {
                "success": proc.returncode == 0 and receipt.is_file(),
                "check_completed": receipt.is_file(),
                "reason": (
                    "completed"
                    if proc.returncode == 0 and receipt.is_file()
                    else "candidate_failure"
                    if proc.returncode != 0
                    else "incomplete_execution"
                ),
                "returncode": proc.returncode,
                "stderr_tail": proc.stderr.decode(errors="replace")[-500:],
                "timeout": False,
                "grader_crash": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": None,
                "stderr_tail": "TIMEOUT",
                "reason": "timeout",
                "timeout": True,
                "grader_crash": False,
            }
        except OSError as exc:
            return {
                "success": None,
                "returncode": None,
                "stderr_tail": f"GRADER_CRASH: {type(exc).__name__}: {exc}",
                "reason": "infrastructure_error",
                "timeout": False,
                "grader_crash": True,
            }


def _grade_one(prompt: str, completion: str, test: str, entry_point: str) -> dict:
    """Refuse untrusted execution until an isolated execution backend is available."""
    return {
        "success": None,
        "returncode": None,
        "stderr_tail": "ISOLATION_REQUIRED: no isolated execution backend is configured",
        "timeout": False,
        "grader_crash": True,
        "reason": "isolation_required",
    }


def main() -> None:
    print(
        "grading disabled: model completions require an isolated execution backend. "
        "Sanitized environment and Python -I do not provide containment. "
        "Historical grades are preserved.",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
