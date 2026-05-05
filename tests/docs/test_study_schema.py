"""Doc parity test for agents/docs/STUDY_SCHEMA.md.

Asserts that every documented `### <field>` sub-heading under the top-level
`## Fields` block (and under each `## <NestedModel>` block) matches the
corresponding Pydantic `model_fields.keys()` in `eval_audit/schema/study.py`.
Drift between schema and docs fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from eval_audit.schema.study import (
    AgentRef,
    Claim,
    CostConfig,
    Design,
    Inference,
    PrimaryOutcome,
    StudySpec,
)


def _doc_path(repo_root: Path) -> Path:
    return repo_root / "agents" / "docs" / "STUDY_SCHEMA.md"


def _extract_field_subheadings(block: str) -> set[str]:
    return set(re.findall(r"^### (\S+)\s*$", block, re.M))


def _extract_top_level_fields(doc: str) -> set[str]:
    """Top-level `## Fields` block, terminated by the next `## ` heading."""
    match = re.search(r"^## Fields\s*$(.*?)(^## |\Z)", doc, re.M | re.S)
    assert match is not None, "STUDY_SCHEMA.md is missing a top-level `## Fields` section"
    return _extract_field_subheadings(match.group(1))


def _extract_nested_model_fields(doc: str, model_name: str) -> set[str]:
    """Nested `## <ModelName>` block, terminated by the next `## ` heading."""
    pattern = rf"^## {re.escape(model_name)}\s*$(.*?)(^## |\Z)"
    match = re.search(pattern, doc, re.M | re.S)
    assert match is not None, f"STUDY_SCHEMA.md is missing a `## {model_name}` section"
    return _extract_field_subheadings(match.group(1))


def test_study_schema__top_level_fields_match_studyspec(repo_root: Path) -> None:
    doc = _doc_path(repo_root).read_text()

    documented = _extract_top_level_fields(doc)
    declared = set(StudySpec.model_fields.keys())

    missing = declared - documented
    extra = documented - declared

    assert not missing, (
        f"STUDY_SCHEMA.md is missing top-level field documentation: {sorted(missing)}. "
        f"Add a `### <field>` sub-heading for each under `## Fields`."
    )
    assert not extra, (
        f"STUDY_SCHEMA.md documents top-level fields that no longer exist on StudySpec: "
        f"{sorted(extra)}. Remove the stale sub-headings."
    )


def test_study_schema__nested_model_fields_match(repo_root: Path) -> None:
    doc = _doc_path(repo_root).read_text()

    nested_models: list[tuple[str, type]] = [
        ("PrimaryOutcome", PrimaryOutcome),
        ("AgentRef", AgentRef),
        ("Design", Design),
        ("Inference", Inference),
        ("CostConfig", CostConfig),
        ("Claim", Claim),
    ]

    for model_name, model_cls in nested_models:
        documented = _extract_nested_model_fields(doc, model_name)
        declared = set(model_cls.model_fields.keys())

        missing = declared - documented
        extra = documented - declared

        assert not missing, (
            f"STUDY_SCHEMA.md `## {model_name}` is missing field documentation: "
            f"{sorted(missing)}. Add a `### <field>` sub-heading for each."
        )
        assert not extra, (
            f"STUDY_SCHEMA.md `## {model_name}` documents fields that no longer exist: "
            f"{sorted(extra)}. Remove the stale sub-headings."
        )


def test_study_schema__mentions_schema_version_default(repo_root: Path) -> None:
    """The doc must surface the version stamp inline so readers see it without
    cross-referencing the source."""
    doc = _doc_path(repo_root).read_text()
    assert "schema_version: 1" in doc, (
        "STUDY_SCHEMA.md should mention `schema_version: 1` literally so readers "
        "see the version stamp inline rather than buried in source."
    )
