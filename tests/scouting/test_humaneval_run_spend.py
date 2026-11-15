"""The HumanEval harness refuses its paid API calls without approval and writes nothing."""

from __future__ import annotations

import importlib.util
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest


def _load_harness(repo_root: Path) -> ModuleType:
    path = repo_root / "scouting" / "humaneval-direct-completion" / "run.py"
    spec = importlib.util.spec_from_file_location("humaneval_run", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def opened_urls(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: calls.append(args))
    return calls


@pytest.mark.parametrize("approved", [False, None, 1, "yes"])
def test_call_api__refuses_without_explicit_approval(
    repo_root: Path, opened_urls: list[object], approved: object
) -> None:
    harness = _load_harness(repo_root)
    with pytest.raises(harness.SpendRefusedError, match="--approved"):
        harness._call_api("key", "model", "prompt", approved=approved)
    assert opened_urls == []
    assert issubclass(harness.SpendRefusedError, SystemExit)
    assert not issubclass(harness.SpendRefusedError, Exception)


def test_main__refuses_before_it_writes_raw_output(
    repo_root: Path,
    opened_urls: list[object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _load_harness(repo_root)
    monkeypatch.setattr(harness, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    with pytest.raises(harness.SpendRefusedError):
        harness.main([])
    assert opened_urls == []
    assert not (tmp_path / "raw").exists()
