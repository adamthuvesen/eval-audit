"""Per-agent summary and cost-quality view sections."""

from __future__ import annotations

from eval_audit.report.formatters import format_currency, format_rate
from eval_audit.report.presentation import StudyPresentation
from eval_audit.stats.results import AnalysisResult


def render_per_agent_summary(result: AnalysisResult, presentation: StudyPresentation) -> list[str]:
    parts: list[str] = ["## Per-agent summary\n"]
    if not presentation.show_cost_columns:
        parts.append(
            "| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low "
            "| success_rate_ci_high |"
        )
        parts.append("|---|---:|---:|---:|---:|---:|")
        for s in result.per_agent:
            parts.append(
                f"| {s.agent_id} | {s.n_graded} | {s.n_errored} | "
                f"{format_rate(s.success_rate)} | {format_rate(s.success_rate_ci_low)} | "
                f"{format_rate(s.success_rate_ci_high)} |"
            )
        parts.append("")
        parts.append(
            "_Cost columns suppressed: cost provenance is `cost_not_available`._"
        )
    else:
        parts.append(
            "| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low "
            "| success_rate_ci_high | total_cost_usd | cost_per_success_usd |"
        )
        parts.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for s in result.per_agent:
            cps = (
                "n/a"
                if s.cost_per_success_usd is None
                else format_currency(s.cost_per_success_usd)
            )
            parts.append(
                f"| {s.agent_id} | {s.n_graded} | {s.n_errored} | "
                f"{format_rate(s.success_rate)} | {format_rate(s.success_rate_ci_low)} | "
                f"{format_rate(s.success_rate_ci_high)} | "
                f"{format_currency(s.total_cost_usd)} | {cps} |"
            )
    parts.append("")
    return parts


def render_cost_quality_view(result: AnalysisResult, presentation: StudyPresentation) -> list[str]:
    parts = ["## Cost-quality view\n"]
    if presentation.pareto_suppressed:
        parts.append(
            "_Cost-quality view suppressed: cost provenance is `cost_not_available`. "
            "See the **Cost provenance caveat** above._"
        )
        parts.append("")
        return parts

    pareto_sorted = sorted(result.pareto_frontier)
    parts.append(
        f"**Pareto frontier (max success_rate, min total_cost_usd):** {pareto_sorted}"
    )
    parts.append("")
    dominated = [
        s.agent_id for s in result.per_agent if s.agent_id not in result.pareto_frontier
    ]
    if dominated:
        parts.append(
            f"Dominated agents: {sorted(dominated)}. Each is dominated by another agent that "
            "achieves at least the same success_rate at no greater total_cost_usd."
        )
    else:
        parts.append("All agents are on the frontier; no dominance to report.")
    parts.append("")
    return parts
