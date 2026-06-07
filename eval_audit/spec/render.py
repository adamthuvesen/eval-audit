"""Deterministic markdown renderer for a StudySpec.

Distinct from `eval_audit.report.markdown` (which renders an *analysis result*).
This renderer presents the *plan* — what will be analyzed, against what
agents, with what inference settings — so an analyst can sanity-check a
study before running it.
"""

from __future__ import annotations

from eval_audit.schema import StudySpec


def render_study_spec(study: StudySpec) -> str:
    """Render a StudySpec as deterministic markdown."""
    parts: list[str] = []

    # 1. Study identity
    parts.append("## Study identity\n")
    parts.append(f"- **id:** `{study.id}`")
    parts.append(f"- **benchmark:** `{study.benchmark}`")
    parts.append(f"- **harness:** `{study.harness}`")
    parts.append(f"- **analysis_mode:** `{study.analysis_mode}`")
    parts.append(f"- **data_observation:** `{study.data_observation}`")
    parts.append("")

    # 2. Primary outcome
    parts.append("## Primary outcome\n")
    parts.append(f"- **name:** `{study.primary_outcome.name}`")
    parts.append(f"- **unit:** `{study.primary_outcome.unit}`")
    parts.append(f"- **direction:** `{study.primary_outcome.direction}`")
    parts.append("")

    # 3. Agents
    parts.append("## Agents\n")
    for agent in study.agents:
        parts.append(f"- `{agent.id}`")
    parts.append("")

    # 4. Design
    parts.append("## Design\n")
    parts.append(f"- **task_sampling:** `{study.design.task_sampling}`")
    parts.append(f"- **run_strategy:** `{study.design.run_strategy}`")
    parts.append(f"- **observed_runs_per_agent:** `{study.design.observed_runs_per_agent}`")
    parts.append(f"- **rerun_policy:** `{study.design.rerun_policy}`")
    parts.append("")

    # 5. Inference plan
    parts.append("## Inference plan\n")
    parts.append(f"- **alpha:** `{study.inference.alpha}`")
    parts.append(f"- **correction_method:** `{study.inference.correction_method}`")
    parts.append(f"- **comparison_family:** `{study.inference.comparison_family}`")
    if study.inference.target_mde is None:
        parts.append("- **target_mde:** none declared")
    else:
        parts.append(
            f"- **target_mde:** `{study.inference.target_mde}` (= {study.inference.target_mde * 100:.2f} pp)"
        )
    parts.append("")

    # 6. Cost view
    parts.append("## Cost view\n")
    parts.append(f"- **primary_view:** `{study.cost.primary_view}`")
    parts.append("- **metrics:**")
    for metric in study.cost.metrics:
        parts.append(f"  - `{metric}`")
    parts.append("")

    # 7. Claims
    parts.append("## Claims\n")
    for claim in study.claims:
        parts.append(f"### `{claim.id}`")
        parts.append(f"- **treatment:** `{claim.treatment}`")
        parts.append(f"- **control:** `{claim.control}`")
        parts.append(f"- **outcome:** `{claim.outcome}`")
        parts.append(f"- **claim text:** {claim.text}")
        parts.append("")

    return "\n".join(parts)
