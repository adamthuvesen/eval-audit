"""Decision documents bound to the committed evidence and declared study identity."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eval_audit.evidence_types import EvidenceSource
    from eval_audit.schema import StudySpec


_EVIDENCE_DECISION_DOCS: dict[tuple[str, str, str, str], str] = {
    (
        "scouting/candidates/gaia/sample.parquet",
        "gaia-hal-generalist",
        "gaia",
        "hal_generalist_agent",
    ): "scouting/gaia-hal-generalist-decision.md",
    (
        "scouting/candidates/tau-bench/sample.parquet",
        "tau-bench-airline-tool-calling",
        "tau_bench",
        "tau_bench_tool_calling",
    ): "scouting/tau-bench-airline-tool-calling-decision.md",
    (
        "examples/swe-bench-verified-openhands/runs.parquet",
        "swe-bench-verified-openhands",
        "swe-bench-verified",
        "swe-bench-verified/openhands-public-submission-v1",
    ): "scouting/swe-bench-verified-openhands-decision.md",
    (
        "examples/terminal-bench-2-mux/runs.parquet",
        "terminal-bench-2-mux",
        "terminal-bench-2",
        "terminal-bench-2/mux-public-submission-v1",
    ): "scouting/terminal-bench-2-mux-decision.md",
    (
        "examples/humaneval-direct-completion/runs.parquet",
        "humaneval-direct-completion",
        "humaneval",
        "eval-audit/humaneval-direct-completion-v1",
    ): "scouting/humaneval-direct-completion-decision.md",
}


def resolve_evidence_decision_doc(
    repo_root: Path, study: StudySpec, source: EvidenceSource | None
) -> tuple[Path, str] | None:
    """Return a decision document only for its registered evidence and study identity."""
    if source is None:
        return None
    fixture_path = source.fixture_path.resolve()
    identity = (study.id, study.benchmark, study.harness)
    for (fixture, study_id, benchmark, harness), document in _EVIDENCE_DECISION_DOCS.items():
        if (
            identity == (study_id, benchmark, harness)
            and fixture_path == (repo_root / fixture).resolve()
        ):
            return repo_root / document, document
    return None
