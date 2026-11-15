"""Risk document attribution follows the selected evidence, independently of encoding."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from eval_audit.checks import check_evidence, check_paths, check_prepared_evidence
from eval_audit.evidence import prepare_evidence
from eval_audit.evidence_types import EvidenceSource
from eval_audit.ingest.generic import load_run_records
from eval_audit.report.presentation import resolve_study_presentation
from eval_audit.report.provenance import (
    extract_residual_risks,
    load_scouting_artifacts,
)
from eval_audit.schema import StudySpec
from eval_audit.stats import analyze


def test_registered_humaneval_canonical_fixture_restores_all_five_risks(repo_root: Path) -> None:
    study_path = repo_root / "studies/humaneval-direct-completion.yaml"
    fixture = repo_root / "examples/humaneval-direct-completion/runs.parquet"
    study = StudySpec.from_yaml(study_path)
    runs = load_run_records(fixture)
    source = EvidenceSource.from_path(fixture, source_kind="canonical")
    result = analyze(study, runs, bootstrap_iterations=30)
    presentation = resolve_study_presentation(study, runs, result, repo_root, source)
    label = "scouting/humaneval-direct-completion-decision.md"
    risks = extract_residual_risks(repo_root / label, label)
    assert len(re.findall(r"^\d+\. ", risks, re.MULTILINE)) == 5
    assert presentation.decision_md_label == label
    assert presentation.residual_risks_text == risks
    assert presentation.cost_recon_data == {}
    assert presentation.source_url == ""
    assert presentation.retrieved_at == ""
    assert presentation.cost_provenance == "partial"

    prepared = prepare_evidence(study, runs)
    readiness_results = [
        check_evidence(study, runs, repo_root=repo_root, source=source),
        check_prepared_evidence(prepared, repo_root=repo_root, source=source),
        check_paths(study_path, fixture, repo_root=repo_root),
    ]
    for readiness in readiness_results:
        check = next(item for item in readiness.checks if item.id == "residual_risks_source")
        assert check.status == "pass"
        assert check.details["path"] == presentation.decision_md_label


@pytest.mark.parametrize("copy_fixture", [False, True])
def test_unbound_canonical_evidence_has_no_registered_document_or_receipts(
    repo_root: Path, tmp_path: Path, copy_fixture: bool
) -> None:
    study = StudySpec.from_yaml(repo_root / "studies/humaneval-direct-completion.yaml")
    fixture = repo_root / "examples/humaneval-direct-completion/runs.parquet"
    if copy_fixture:
        copied = tmp_path / "runs.parquet"
        copied.write_bytes(fixture.read_bytes())
        fixture = copied
    else:
        study = study.model_copy(update={"id": "different-study"})
    runs = load_run_records(fixture)
    source = EvidenceSource.from_path(fixture, source_kind="canonical")
    result = analyze(study, runs, bootstrap_iterations=30)
    presentation = resolve_study_presentation(study, runs, result, repo_root, source)
    assert presentation.decision_md_label is None
    assert "HumanEval is in training data" not in presentation.residual_risks_text
    assert presentation.cost_recon_data == {}
    readiness = check_evidence(study, runs, repo_root=repo_root, source=source)
    check = next(item for item in readiness.checks if item.id == "residual_risks_source")
    assert check.status == "fail"
    assert check.severity == "warning"


def test_canonical_source_never_imports_adapter_receipts(repo_root: Path) -> None:
    directory = repo_root / "examples/humaneval-direct-completion"
    source = EvidenceSource.from_path(
        directory / "runs.parquet", source_kind="canonical", source_dir=directory
    )
    scouting = load_scouting_artifacts(repo_root, source)
    assert scouting.cost_recon_data == {}
    assert scouting.source_url == ""
    assert scouting.retrieved_at == ""
