"""Source and study identity bindings for scouting decision documents."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from eval_audit.evidence_types import EvidenceSource
from eval_audit.schema import StudySpec
from eval_audit.scouting_paths import resolve_evidence_decision_doc


@pytest.mark.parametrize(
    "study_name,fixture",
    [
        ("gaia-hal-generalist", "scouting/candidates/gaia/sample.parquet"),
        ("tau-bench-airline-tool-calling", "scouting/candidates/tau-bench/sample.parquet"),
        ("swe-bench-verified-openhands", "examples/swe-bench-verified-openhands/runs.parquet"),
        ("terminal-bench-2-mux", "examples/terminal-bench-2-mux/runs.parquet"),
        ("humaneval-direct-completion", "examples/humaneval-direct-completion/runs.parquet"),
    ],
)
def test_committed_evidence_resolves_its_registered_document(
    repo_root: Path, study_name: str, fixture: str
) -> None:
    study = StudySpec.from_yaml(repo_root / "studies" / f"{study_name}.yaml")
    source = EvidenceSource.from_path(repo_root / fixture, source_kind="canonical")
    expected = f"scouting/{study_name}-decision.md"
    assert resolve_evidence_decision_doc(repo_root, study, source) == (
        repo_root / expected,
        expected,
    )


@pytest.mark.parametrize("field", ["id", "benchmark", "harness"])
def test_registered_path_does_not_supply_risks_for_a_different_study_identity(
    repo_root: Path, field: str
) -> None:
    study = StudySpec.from_yaml(repo_root / "studies/humaneval-direct-completion.yaml")
    study = study.model_copy(update={field: "unregistered-identity"})
    source = EvidenceSource.from_path(
        repo_root / "examples/humaneval-direct-completion/runs.parquet", source_kind="canonical"
    )
    assert resolve_evidence_decision_doc(repo_root, study, source) is None


@pytest.mark.parametrize("source_kind", ["canonical", "adapter"])
def test_identical_copied_evidence_does_not_inherit_registered_risks(
    repo_root: Path, tmp_path: Path, source_kind: Literal["canonical", "adapter"]
) -> None:
    study = StudySpec.from_yaml(repo_root / "studies/humaneval-direct-completion.yaml")
    fixture = repo_root / "examples/humaneval-direct-completion/runs.parquet"
    copied = tmp_path / "copied.parquet"
    copied.write_bytes(fixture.read_bytes())
    source = EvidenceSource.from_path(copied, source_kind=source_kind, source_dir=tmp_path)
    original = EvidenceSource.from_path(fixture, source_kind="canonical")
    assert source.fixture_sha256 == original.fixture_sha256
    assert resolve_evidence_decision_doc(repo_root, study, source) is None


def test_relative_and_absolute_paths_resolve_to_the_same_binding(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo_root)
    study = StudySpec.from_yaml("studies/humaneval-direct-completion.yaml")
    fixture = Path("examples/humaneval-direct-completion/runs.parquet")
    relative = EvidenceSource.from_path(fixture, source_kind="canonical")
    absolute = EvidenceSource.from_path(fixture.resolve(), source_kind="canonical")
    assert resolve_evidence_decision_doc(Path(), study, relative) == (
        Path("scouting/humaneval-direct-completion-decision.md"),
        "scouting/humaneval-direct-completion-decision.md",
    )
    assert resolve_evidence_decision_doc(
        repo_root, study, relative
    ) == resolve_evidence_decision_doc(repo_root, study, absolute)


def test_no_source_does_not_inherit_risks_by_benchmark_name(repo_root: Path) -> None:
    study = StudySpec.from_yaml(repo_root / "studies/gaia-hal-generalist.yaml")
    assert resolve_evidence_decision_doc(repo_root, study, None) is None
