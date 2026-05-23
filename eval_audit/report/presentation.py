"""Study-level presentation policy for markdown reports and summary.json."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from eval_audit.report import ReportContractError
from eval_audit.report.provenance import load_scouting_artifacts, resolve_decision_artifacts
from eval_audit.schema import StudySpec
from eval_audit.schema.enums import CostProvenance
from eval_audit.stats.results import AnalysisResult


@dataclass(frozen=True)
class StudyPresentation:
    cost_provenance: str
    pareto_suppressed: bool
    show_cost_columns: bool
    cost_gap_sensitivity_applicable: bool
    hedge_on_cost_allowed: bool
    source_fixture_rel: str
    source_url: str
    retrieved_at: str
    residual_risks_text: str
    decision_md_label: str
    cost_recon_data: dict


def row_level_cost_provenance(runs: pl.DataFrame) -> str:
    """Strict row-level cost provenance for preregistered and BYO studies."""
    if "cost_provenance" not in runs.columns or runs.is_empty():
        return "n/a"
    values = sorted(str(v) for v in runs["cost_provenance"].unique().to_list())
    if len(values) == 1:
        return values[0]
    raise ReportContractError(
        f"ambiguous cost_provenance across runs frame: {values}"
    )


def resolve_report_cost_provenance(
    study: StudySpec,
    runs: pl.DataFrame,
    cost_recon_data: dict,
) -> str:
    """Resolve headline cost provenance with the same priority as render_report."""
    if cost_recon_data:
        return str(cost_recon_data.get("outcome", "n/a"))
    if study.analysis_mode == "preregistered":
        return row_level_cost_provenance(runs)
    try:
        row_level = row_level_cost_provenance(runs)
    except ReportContractError:
        return "n/a"
    if row_level == CostProvenance.COST_NOT_AVAILABLE.value:
        return row_level
    return "n/a"


def resolve_study_presentation(
    study: StudySpec,
    runs: pl.DataFrame,
    result: AnalysisResult,
    repo_root: Path,
) -> StudyPresentation:
    """Build presentation flags and provenance metadata for one audit render."""
    repo_root = Path(repo_root)
    _decision_md, decision_md_label, residual_risks_text = resolve_decision_artifacts(
        repo_root, study
    )
    scouting = load_scouting_artifacts(study, repo_root)
    cost_provenance = resolve_report_cost_provenance(
        study, runs, scouting.cost_recon_data
    )
    pareto_suppressed = result.pareto_status == "suppressed_cost_not_available"
    cost_suppressed = cost_provenance == CostProvenance.COST_NOT_AVAILABLE.value
    show_cost_columns = not pareto_suppressed and not cost_suppressed
    return StudyPresentation(
        cost_provenance=cost_provenance,
        pareto_suppressed=pareto_suppressed,
        show_cost_columns=show_cost_columns,
        cost_gap_sensitivity_applicable=not pareto_suppressed,
        hedge_on_cost_allowed=not pareto_suppressed and not cost_suppressed,
        source_fixture_rel=scouting.source_fixture_rel,
        source_url=scouting.source_url,
        retrieved_at=scouting.retrieved_at,
        residual_risks_text=residual_risks_text,
        decision_md_label=decision_md_label,
        cost_recon_data=scouting.cost_recon_data,
    )
