"""The committed RunRecord JSON schema is the contract exporters copy and test against."""

from __future__ import annotations

import json
from pathlib import Path

from eval_audit.schema import RunRecord


def test_run_record_snapshot__matches_model(repo_root: Path) -> None:
    committed = json.loads((repo_root / "docs" / "run-record.schema.json").read_text())
    assert committed == RunRecord.model_json_schema(), (
        "docs/run-record.schema.json drifted from RunRecord. Regenerate it with "
        "`uv run --locked eval-audit spec schema --model run > docs/run-record.schema.json`, "
        "then copy it into each exporter's test fixtures (heist, counterfact)."
    )
