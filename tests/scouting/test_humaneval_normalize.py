"""Unknown measurements and unverified historical grades cannot replace recorded evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import polars as pl
import pytest

from eval_audit.schema import RunRecord


def _load_normalizer(repo_root: Path) -> ModuleType:
    path = repo_root / "scouting" / "humaneval-direct-completion" / "normalize.py"
    spec = importlib.util.spec_from_file_location("humaneval_normalize", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record() -> dict[str, Any]:
    return {
        "agent_id": "test-agent",
        "agent_short": "test",
        "model_id": "test-model",
        "task_id": "HumanEval/1",
        "run_id": "test-1",
        "outcome_status": "graded",
        "success": True,
        "ok": True,
        "payload": {"usage": {"input_tokens": 10, "output_tokens": 20}},
        "started_at": "2026-01-01T00:00:00Z",
        "system_prompt": "test prompt",
        "temperature": 0,
        "max_tokens": 100,
        "grader": {"check_completed": True},
    }


def _setup(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: dict[str, Any]
) -> ModuleType:
    module = _load_normalizer(repo_root)
    graded = tmp_path / "graded"
    graded.mkdir()
    (graded / "record.json").write_text(json.dumps(record))
    price_table = tmp_path / "prices.yaml"
    price_table.write_text(
        'date: "2026-01-01"\nmodels:\n  test-model:\n    input_per_mtok: 1\n    output_per_mtok: 2\n'
    )
    monkeypatch.setattr(module, "GRADED_DIR", graded)
    monkeypatch.setattr(module, "PRICE_TABLE_PATH", price_table)
    monkeypatch.setattr(module, "OUT_PATH", tmp_path / "runs.parquet")
    monkeypatch.setattr(sys, "argv", ["normalize"])
    return module


@pytest.mark.parametrize(
    ("missing", "error"),
    [
        ("usage", "missing provider usage"),
        ("started_at", "missing started_at"),
        ("grader", "no completion receipt"),
    ],
)
def test_normalize__unknown_evidence_preserves_output(
    missing: str, error: str, repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record()
    if missing == "usage":
        record["payload"].pop("usage")
    else:
        record.pop(missing)
    module = _setup(repo_root, tmp_path, monkeypatch, record)
    module.OUT_PATH.write_bytes(b"recorded-evidence")
    with pytest.raises(ValueError, match=error):
        module.main()
    assert module.OUT_PATH.read_bytes() == b"recorded-evidence"


def test_normalize__validates_staged_schema_and_requires_accepting_change(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record()
    module = _setup(repo_root, tmp_path, monkeypatch, record)
    module.main()
    first = module.OUT_PATH.read_bytes()
    frame = pl.read_parquet(module.OUT_PATH)
    assert frame.columns == list(RunRecord.model_fields)
    assert frame["tokens_in"].to_list() == [10]
    record["success"] = False
    (module.GRADED_DIR / "record.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="differs from existing evidence"):
        module.main()
    assert module.OUT_PATH.read_bytes() == first
