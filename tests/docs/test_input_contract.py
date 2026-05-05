"""Doc parity test for agents/docs/INPUT_CONTRACT.md.

Asserts that the documented `### <field>` sub-headings under `## Fields`
match `RunRecord.model_fields.keys()` exactly. Drift between schema and
docs fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from eval_audit.schema import RunRecord


def test_input_contract__field_list_matches_run_record_schema(repo_root: Path) -> None:
    doc = (repo_root / "agents" / "docs" / "INPUT_CONTRACT.md").read_text()

    fields_match = re.search(r"^## Fields\s*$(.*?)(^## |\Z)", doc, re.M | re.S)
    assert fields_match is not None, "INPUT_CONTRACT.md is missing a `## Fields` section"

    fields_block = fields_match.group(1)
    documented = set(re.findall(r"^### (\S+)\s*$", fields_block, re.M))

    declared = set(RunRecord.model_fields.keys())

    missing = declared - documented
    extra = documented - declared

    assert not missing, (
        f"INPUT_CONTRACT.md is missing field documentation: {sorted(missing)}. "
        f"Add a `### <field>` sub-heading for each."
    )
    assert not extra, (
        f"INPUT_CONTRACT.md documents fields that no longer exist on RunRecord: "
        f"{sorted(extra)}. Remove the stale sub-headings."
    )
