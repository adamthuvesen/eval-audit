"""Shared resolution helpers for scouting-keyed paths.

Both the readiness checker (`eval_audit.checks`) and the markdown renderer
(`eval_audit.report.markdown`) need to find the per-study scouting decision
document. The resolution rule is the same in both places, so it lives here
to avoid drift.

Resolution order for the residual-risks decision document:
    1. Benchmark alias (preserves historical filenames such as
       ``gaia-hal-generalist-decision.md`` and the ``tau-bench`` hyphenation
       used by the scouting fixture directory).
    2. ``scouting/<benchmark>-decision.md`` if it exists.
    3. ``scouting/<study_id>-decision.md`` as the fallback for
       controlled-evidence exhibits whose decision doc is keyed by study id
       rather than by a public-benchmark name (e.g. HumanEval Direct
       Completion uses ``scouting/humaneval-direct-completion-decision.md``).
"""

from __future__ import annotations

from pathlib import Path

DECISION_DOC_ALIAS: dict[str, str] = {
    "gaia": "gaia-hal-generalist-decision.md",
    "tau_bench": "tau-bench-airline-tool-calling-decision.md",
}


def resolve_decision_doc(
    repo_root: Path, benchmark: str, study_id: str
) -> tuple[Path, str]:
    """Return ``(path, repo-relative label)`` for the study's decision doc."""
    if benchmark in DECISION_DOC_ALIAS:
        filename = DECISION_DOC_ALIAS[benchmark]
        return repo_root / "scouting" / filename, f"scouting/{filename}"
    by_benchmark = repo_root / "scouting" / f"{benchmark}-decision.md"
    if by_benchmark.exists():
        return by_benchmark, f"scouting/{benchmark}-decision.md"
    by_study = repo_root / "scouting" / f"{study_id}-decision.md"
    return by_study, f"scouting/{study_id}-decision.md"
