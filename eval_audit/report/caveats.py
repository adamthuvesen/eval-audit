"""Canonical cost-provenance caveat copy for markdown and summary.json."""

from __future__ import annotations

from eval_audit.report.presentation import StudyPresentation
from eval_audit.schema.enums import CostProvenance


def cost_caveat_one_liner(
    presentation: StudyPresentation,
    *,
    treatment_cost: float | None,
    control_cost: float | None,
) -> str:
    """One-line cost caveat for summary.json claim rows."""
    if presentation.cost_provenance == CostProvenance.COST_NOT_AVAILABLE.value:
        return (
            "cost provenance is cost_not_available; cost-derived views and "
            "cost-driven verdict branches are suppressed"
        )
    if presentation.cost_provenance == CostProvenance.AS_REPORTED_ONLY.value:
        return (
            "cost provenance is as_reported_only; costs come from reported totals "
            "rather than reconciled per-task reconstruction"
        )
    if treatment_cost is None or control_cost is None:
        return "no reliable cost ratio is available"
    if control_cost > 0:
        return f"treatment cost is {treatment_cost / control_cost:.2f}x control"
    return "control cost is zero, so the cost ratio is undefined"


def render_as_reported_only_caveat(cost_recon_data: dict) -> list[str]:
    """Markdown lines for the as_reported_only cost provenance subsection."""
    parts: list[str] = []
    parts.append("### Cost provenance caveat\n")
    parts.append("> ⚠️ Cost provenance: as_reported_only")
    parts.append("")
    parts.append(
        "HAL's reported run-total cost is used directly because per-task cost "
        "reconstruction from token counts × pinned provider prices does not "
        "reconcile to HAL's reported total within the toolkit's 1% tolerance. "
        "Per-task cost analyses are therefore unavailable for this study; "
        "cost figures below are derived from the reported run-total divided by "
        "graded successes."
    )
    parts.append("")
    parts.append("**Divergences (per run):**\n")
    for d in cost_recon_data.get("divergences", []):
        agent_id = d.get("agent_id", "")
        reported = float(d.get("reported_cost_usd", 0.0))
        recon = float(d.get("reconstructed_cost_usd", 0.0))
        note = d.get("hypothesis", "")
        parts.append(
            f"- {agent_id} — reported ${reported:.2f}, reconstructed ${recon:.2f} (note: {note})"
        )
    parts.append("")
    parts.append("**Caveats:**\n")
    for c in cost_recon_data.get("caveats", []):
        parts.append(f"- {c}")
    parts.append("")
    return parts


def render_cost_not_available_caveat(suppressed_agents: list[str]) -> list[str]:
    """Markdown lines for the cost_not_available provenance subsection."""
    parts: list[str] = []
    parts.append("### Cost provenance caveat\n")
    parts.append("> ⚠️ Cost provenance: cost_not_available")
    parts.append("")
    parts.append(
        "The upstream artifacts for this study do not expose complete, stable "
        "cost fields. Per-task cost cannot be reconstructed with the report's "
        "pinned price policy, and no complete per-run reported total is available. "
        "Rather than smuggle in zeros, this report **suppresses** every "
        "cost-derived view: per-agent `total_cost_usd` and `cost_per_success_usd` "
        "columns are omitted from the Per-agent summary, the Cost-quality view "
        "(Pareto frontier) is suppressed, and `decision_impact` cannot return "
        "`hedge_on_cost` for any claim in this study."
    )
    parts.append("")
    if suppressed_agents:
        parts.append("**Cost-suppressed agents:**\n")
        for agent_id in suppressed_agents:
            parts.append(f"- `{agent_id}`")
        parts.append("")
    parts.append(
        "Cost-related residual risks are inherited from the scouting decision "
        "document (see Residual risks below)."
    )
    parts.append("")
    return parts
