"""Scouting artifact loading and residual-risk extraction for reports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from eval_audit.fixtures import benchmark_dir_name
from eval_audit.schema import StudySpec
from eval_audit.scouting_paths import resolve_decision_doc


@dataclass(frozen=True)
class ScoutingArtifacts:
    cost_recon_data: dict
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


def load_scouting_artifacts(study: StudySpec, repo_root: Path) -> ScoutingArtifacts:
    """Load scouting candidate paths and public-submission fallbacks."""
    benchmark_dir = benchmark_dir_name(study.benchmark)
    cost_recon_path = (
        repo_root / "scouting" / "candidates" / benchmark_dir / "cost-reconciliation.json"
    )
    provenance_path = repo_root / "scouting" / "candidates" / benchmark_dir / "provenance.json"
    cost_recon_data: dict = {}
    if cost_recon_path.exists():
        cost_recon_data = json.loads(cost_recon_path.read_text())

    source_fixture_rel = f"scouting/candidates/{benchmark_dir}/sample.parquet"
    source_url = ""
    retrieved_at = ""
    if provenance_path.exists():
        prov = json.loads(provenance_path.read_text())
        source_url = prov.get("source_url", "")
        retrieved_at = prov.get("retrieved_at", "")
    else:
        examples_provenance = repo_root / "examples" / study.id / "provenance.json"
        if examples_provenance.exists():
            prov = json.loads(examples_provenance.read_text())
            source_fixture_rel = f"examples/{study.id}/runs.parquet"
            sources = prov.get("sources") or []
            if sources:
                source_url = sources[0].get("url", "")
            retrieved_at = prov.get("fetched_at_utc", "")

    return ScoutingArtifacts(
        cost_recon_data=cost_recon_data,
        source_fixture_rel=source_fixture_rel,
        source_url=source_url,
        retrieved_at=retrieved_at,
    )


def resolve_decision_artifacts(repo_root: Path, study: StudySpec) -> tuple[str, str]:
    """Return the decision doc's repo-relative label and residual risks text."""
    decision_md, decision_md_label = resolve_decision_doc(repo_root, study.benchmark, study.id)
    residual_risks_text = extract_residual_risks(decision_md, decision_md_label)
    return decision_md_label, residual_risks_text
