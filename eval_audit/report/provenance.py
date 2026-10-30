"""Scouting artifact loading and residual-risk extraction for reports."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from eval_audit.report import ReportContractError
from eval_audit.schema import StudySpec
from eval_audit.scouting_paths import resolve_evidence_decision_doc


@dataclass(frozen=True)
class EvidenceSource:
    fixture_path: Path
    fixture_sha256: str
    source_kind: Literal["canonical", "adapter"]
    source_dir: Path | None = None

    def display_path(self, repo_root: Path) -> str:
        try:
            return str(self.fixture_path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            return str(self.fixture_path.resolve())

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        source_kind: Literal["canonical", "adapter"],
        source_dir: Path | None = None,
    ) -> EvidenceSource:
        return cls(path, hashlib.sha256(path.read_bytes()).hexdigest(), source_kind, source_dir)


@dataclass(frozen=True)
class ScoutingArtifacts:
    cost_recon_data: dict[str, Any]
    source_fixture_rel: str
    source_url: str
    retrieved_at: str


def extract_residual_risks(decision_md_path: Path, relative_label: str) -> str:
    """Extract the bulleted residual-risks list from the resolved scouting decision doc."""
    if not decision_md_path.exists():
        return (
            f"_(no scouting decision document at {relative_label}; residual risks not surfaced.)_"
        )
    text = decision_md_path.read_text()
    start_match = re.search(r"^## Residual risks\s*$", text, flags=re.MULTILINE)
    if not start_match:
        return "(no residual risks found in scouting decision document)"
    start = start_match.end()
    end_match = re.search(r"^## ", text[start:], flags=re.MULTILINE)
    end = start + (end_match.start() if end_match else len(text) - start)
    return text[start:end].strip()


def load_scouting_artifacts(
    repo_root: Path, source: EvidenceSource | None = None
) -> ScoutingArtifacts:
    """Read receipts only from the explicitly selected adapter source."""
    if source is None:
        return ScoutingArtifacts({}, "in-memory evidence", "", "")
    label = source.display_path(repo_root)
    if source.source_kind == "canonical" or source.source_dir is None:
        return ScoutingArtifacts({}, label, "", "")
    cost_path = source.source_dir / "cost-reconciliation.json"
    provenance_path = source.source_dir / "provenance.json"
    cost = _read_receipt(cost_path) if cost_path.exists() else {}
    provenance = _read_receipt(provenance_path) if provenance_path.exists() else {}
    source_url = provenance.get("source_url", "")
    if not source_url and provenance.get("sources"):
        sources = provenance["sources"]
        if not isinstance(sources, list) or not isinstance(sources[0], dict):
            raise ReportContractError(f"{provenance_path}: sources must contain source objects")
        source_url = sources[0].get("url", "")
    retrieved_at = provenance.get("retrieved_at", provenance.get("fetched_at_utc", ""))
    if not isinstance(source_url, str) or not isinstance(retrieved_at, str):
        raise ReportContractError(
            f"{provenance_path}: source URL and retrieval date must be strings"
        )
    return ScoutingArtifacts(cost, label, source_url, retrieved_at)


def _read_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ReportContractError(f"cannot read evidence receipt {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReportContractError(f"{path}: expected a JSON object")
    return payload


def resolve_decision_artifacts(
    repo_root: Path, study: StudySpec, source: EvidenceSource | None = None
) -> tuple[str | None, str]:
    """Return residual risks only for the selected evidence's registered document."""
    decision = resolve_evidence_decision_doc(repo_root, study, source)
    if decision is None:
        return (
            None,
            "(no residual-risk document supplied with this evidence)",
        )
    decision_md, decision_md_label = decision
    return decision_md_label, extract_residual_risks(decision_md, decision_md_label)
