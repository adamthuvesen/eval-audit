"""Acceptance tests for the HumanEval Direct Completion grader's subprocess sandbox.

The grader executes untrusted model-generated code. These tests verify the
v0 trust boundary: the subprocess runs with a sanitized environment (no
ANTHROPIC_API_KEY, no HOME, no parent secrets) and Python isolated mode
(-I, which ignores user site-packages and PYTHONPATH).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GRADE_PATH = REPO_ROOT / "scouting" / "humaneval-direct-completion" / "grade.py"


def _load_grade_module():
    spec = importlib.util.spec_from_file_location("humaneval_direct_completion_grade", GRADE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load grade.py at {GRADE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grader_env__scrubs_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The grader subprocess MUST NOT see ANTHROPIC_API_KEY from the parent env.

    A malicious or accidental completion that reads os.environ would
    otherwise exfiltrate secrets through stdout / stderr.
    """
    grade = _load_grade_module()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-secret-VALUE-XYZ")

    sandboxed = grade._sandboxed_env()

    assert "ANTHROPIC_API_KEY" not in sandboxed
    assert sandboxed.get("PATH"), "PATH should be forwarded so the interpreter resolves"


def test_grader_env__scrubs_home_and_pythonpath(monkeypatch: pytest.MonkeyPatch) -> None:
    """HOME and PYTHONPATH must not leak into the grader subprocess."""
    grade = _load_grade_module()
    monkeypatch.setenv("HOME", "/tmp/fake-home")
    monkeypatch.setenv("PYTHONPATH", "/tmp/fake-pythonpath")

    sandboxed = grade._sandboxed_env()

    assert "HOME" not in sandboxed
    assert "PYTHONPATH" not in sandboxed


def test_grader_subprocess__cannot_read_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An end-to-end check: a completion that reads ANTHROPIC_API_KEY sees nothing.

    Builds a candidate program that prints the env var, runs it through the
    grader, and asserts the secret is absent from stderr/stdout.
    """
    grade = _load_grade_module()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-secret-VALUE-XYZ")

    # A "completion" that reads the secret and writes it as stdout, then
    # raises a controlled error so returncode != 0 and stderr captures the
    # leaked value (if any).
    prompt = "def report():\n    pass\n"
    completion = (
        "    import os, sys\n"
        "    leaked = os.environ.get('ANTHROPIC_API_KEY', '__MISSING__')\n"
        "    sys.stderr.write(f'leaked={leaked}\\n')\n"
        "    raise SystemExit(0 if leaked == '__MISSING__' else 1)\n"
    )
    test = "def check(_):\n    report()\n"

    grade_result = grade._grade_one(
        prompt=prompt, completion=completion, test=test, entry_point="report"
    )

    # The candidate exits 0 only if the env var was absent — i.e. the sandbox
    # successfully scrubbed it.
    assert grade_result["success"] is True, (
        f"sandbox failed to scrub ANTHROPIC_API_KEY: stderr_tail={grade_result['stderr_tail']!r}"
    )
    assert "sk-ant-test-secret-VALUE-XYZ" not in grade_result["stderr_tail"]


def test_grader_subprocess__stdlib_imports_still_work() -> None:
    """Sanity: -I mode must not break stdlib imports the candidates rely on.

    The HumanEval candidates use math, typing, collections, copy, string,
    random — all stdlib. Verify a representative stdlib import succeeds in
    the sandboxed subprocess.
    """
    grade = _load_grade_module()

    prompt = "def f():\n    pass\n"
    completion = (
        "    import math\n"
        "    import collections\n"
        "    from typing import List\n"
        "    assert math.pi > 3\n"
        "    assert isinstance(collections.OrderedDict(), dict)\n"
    )
    test = "def check(_):\n    f()\n"

    grade_result = grade._grade_one(
        prompt=prompt, completion=completion, test=test, entry_point="f"
    )

    assert grade_result["success"] is True, (
        f"-I mode broke stdlib imports: stderr_tail={grade_result['stderr_tail']!r}"
    )
