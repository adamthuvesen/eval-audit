"""Host execution is refused. Only repository-authored fixtures use the private helper."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADE_PATH = REPO_ROOT / "scouting" / "humaneval-direct-completion" / "grade.py"


def _load_grade_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("humaneval_direct_completion_grade", GRADE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grader__refuses_untrusted_host_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    grade = _load_grade_module()

    def unexpected_execution(*_args: object, **_kwargs: object) -> None:
        pytest.fail("untrusted host execution must not start")

    monkeypatch.setattr(grade.subprocess, "run", unexpected_execution)
    result = grade.grade_one("", "", "", "f")
    assert result["success"] is None
    assert result["grader_crash"] is True
    assert result["reason"] == "isolation_required"


def test_grader_cli__refuses_before_reading_or_writing(repo_root: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "--locked", "python", str(GRADE_PATH)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "isolated execution backend" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("completion", "expected_success", "reason"),
    [
        ("    return 1\n", True, "completed"),
        ("    return 2\n", False, "candidate_failure"),
        ("    import sys\n    sys.exit(0)\n", False, "incomplete_execution"),
    ],
)
def test_trusted_fixture__requires_completed_check(
    completion: str, expected_success: bool, reason: str
) -> None:
    grade = _load_grade_module()
    result = grade.grade_trusted_fixture(
        prompt="def f():\n",
        completion=completion,
        test="def check(fn):\n    assert fn() == 1\n",
        entry_point="f",
    )
    assert result["success"] is expected_success
    assert result["reason"] == reason
    assert result["grader_crash"] is False


def test_trusted_fixture__reduces_environment_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    grade = _load_grade_module()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    monkeypatch.setenv("PYTHONPATH", "/tmp/test-pythonpath")
    assert "HOME" not in grade._trusted_fixture_env()
    result = grade.grade_trusted_fixture(
        prompt="def f():\n",
        completion=(
            "    import os, math\n"
            "    assert 'ANTHROPIC_API_KEY' not in os.environ\n"
            "    assert 'PYTHONPATH' not in os.environ\n"
            "    return math.floor(1.5)\n"
        ),
        test="def check(fn):\n    assert fn() == 1\n",
        entry_point="f",
    )
    assert result["success"] is True


def test_trusted_fixture__setup_crash_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    grade = _load_grade_module()

    def raise_os_error(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated subprocess setup failure")

    monkeypatch.setattr(grade.subprocess, "run", raise_os_error)
    result = grade.grade_trusted_fixture("def f():\n", "    return 1", "def check(fn): pass", "f")
    assert result["success"] is None
    assert result["reason"] == "infrastructure_error"


def test_trusted_fixture__timeout_is_a_model_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    grade = _load_grade_module()
    monkeypatch.setattr(grade, "GRADE_TIMEOUT_S", 0.05)
    result = grade.grade_trusted_fixture(
        "def f():\n", "    while True: pass", "def check(fn): fn()", "f"
    )
    assert result["success"] is False
    assert result["reason"] == "timeout"
    assert result["grader_crash"] is False
