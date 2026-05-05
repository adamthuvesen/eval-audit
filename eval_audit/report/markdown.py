"""Deterministic markdown report renderer for declared-claim reanalyses."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import polars as pl

from eval_audit.fixtures import benchmark_dir_name
from eval_audit.ingest._prices import PRICE_TABLE_PINNED_AT
from eval_audit.report import ReportContractError
from eval_audit.report.decisions import (
    DECISION_IMPACT_VOCAB,
    ClaimContext,
    decision_impact,
    direction_matches_claim,
)
from eval_audit.schema import StudySpec
from eval_audit.stats import AnalysisResult, analyze

_STATUS_VOCAB = {"supported", "unsupported", "inconclusive"}


def _claim_status(rejects: bool, direction_matches: bool, ci_crosses_zero: bool) -> str:
    if rejects and direction_matches:
        return "supported"
    if rejects and not direction_matches:
        return "unsupported"
    if ci_crosses_zero:
        return "inconclusive"
    return "inconclusive"


def _format_pp(delta: float) -> str:
    return f"{delta * 100:+.2f} pp"


def _format_currency(value: float) -> str:
    return f"${value:.2f}"


def _format_rate(value: float) -> str:
    return f"{value:.4f}"


def _validate_report_outcome(study: StudySpec) -> None:
    if (
        study.primary_outcome.name != "success_rate"
        or study.primary_outcome.direction != "higher_is_better"
    ):
        raise ValueError(
            "v0 reports support only primary_outcome.name='success_rate' "
            "with direction='higher_is_better'"
        )
    for claim in study.claims:
        if claim.outcome != "success_rate":
            raise ValueError(
                f"v0 reports support only claim outcome 'success_rate' "
                f"(claim_id={claim.id!r}, outcome={claim.outcome!r})"
            )


# Aliases for the residual-risks decision-document path. The renderer resolves
# `scouting/<benchmark>-decision.md` by default; the aliases preserve Exhibit A's
# historical filename and translate `tau_bench` -> `tau-bench` to match the
# scouting fixture's hyphenated directory convention.
_DECISION_DOC_ALIAS = {
    "gaia": "exhibit-a-decision.md",
    "tau_bench": "tau-bench-decision.md",
}


def _resolve_decision_doc(repo_root: Path, benchmark: str) -> tuple[Path, str]:
    """Return (path, relative_label) for the per-benchmark scouting decision doc."""
    filename = _DECISION_DOC_ALIAS.get(benchmark, f"{benchmark}-decision.md")
    return repo_root / "scouting" / filename, f"scouting/{filename}"


def _extract_residual_risks(decision_md_path: Path, relative_label: str) -> str:
    """Extract the bulleted residual-risks list from the resolved scouting decision doc.

    Falls back to a single placeholder line when the file does not exist, so the
    Residual risks section preserves the seven-section shape contract.
    """
    if not decision_md_path.exists():
        return (
            f"_(no scouting decision document at {relative_label}; "
            "residual risks not surfaced.)_"
        )
    text = decision_md_path.read_text()
    start_match = re.search(r"^## Residual risks\s*$", text, flags=re.MULTILINE)
    if not start_match:
        return "(no residual risks found in scouting decision document)"
    start = start_match.end()
    end_match = re.search(r"^## ", text[start:], flags=re.MULTILINE)
    end = start + (end_match.start() if end_match else len(text) - start)
    block = text[start:end].strip()
    return block


def render_claim_row(row: dict) -> str:
    """Render a single claim row, validating its decision_impact value.

    Raises ReportContractError if the row's decision_impact is not in the controlled vocabulary.
    The target_mde column is included only when row['target_mde'] is set.
    """
    di = row.get("decision_impact")
    if di not in DECISION_IMPACT_VOCAB:
        raise ReportContractError(
            f"decision_impact={di!r} is not in controlled vocabulary {DECISION_IMPACT_VOCAB}"
        )
    status = row.get("status")
    if status not in _STATUS_VOCAB:
        raise ReportContractError(
            f"status={status!r} is not in controlled vocabulary {sorted(_STATUS_VOCAB)}"
        )
    if "target_mde" in row:
        return (
            f"| {row['claim_id']} | {row['mode']} | {row['status']} | "
            f"{row['effect']} | {row['target_mde']} | "
            f"{row['adjusted_result']} | {row['decision_impact']} |"
        )
    return (
        f"| {row['claim_id']} | {row['mode']} | {row['status']} | "
        f"{row['effect']} | {row['adjusted_result']} | {row['decision_impact']} |"
    )


def render_report(
    result: AnalysisResult,
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    clock: Callable[[], datetime],
    git_commit: str,
    fixture_sha256: str,
    repo_root: Path,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
) -> str:
    """Render a deterministic markdown report for one declared-claim reanalysis.

    `runs` is required so the verdict-sensitivity sub-block can recompute the
    errored-row-excluded perturbation against the original frame. Bootstrap
    parameters are passed through so the perturbed bootstrap matches the
    baseline's iteration count and seed.
    """
    _validate_report_outcome(study)
    decision_md, decision_md_label = _resolve_decision_doc(repo_root, study.benchmark)
    benchmark_dir = benchmark_dir_name(study.benchmark)
    cost_recon = (
        repo_root
        / "scouting"
        / "candidates"
        / benchmark_dir
        / "cost-reconciliation.json"
    )
    provenance = (
        repo_root / "scouting" / "candidates" / benchmark_dir / "provenance.json"
    )

    rendered_at = clock().isoformat()

    parts: list[str] = []

    # 1. Study
    parts.append("## Study\n")
    primary_claim = study.claims[0]
    parts.append(f"- **id:** `{study.id}`")
    parts.append(f"- **benchmark:** `{study.benchmark}`")
    parts.append(f"- **harness:** `{study.harness}`")
    parts.append(f"- **analysis_mode:** `{study.analysis_mode}`")
    parts.append(f"- **data_observation:** `{study.data_observation}`")
    parts.append(f"- **claim:** {primary_claim.text}")
    parts.append("")

    # 2. Provenance
    parts.append("## Provenance\n")
    cost_provenance_class = "n/a"
    cost_recon_data: dict = {}
    if cost_recon.exists():
        cost_recon_data = json.loads(cost_recon.read_text())
        cost_provenance_class = cost_recon_data.get("outcome", "n/a")
    source_url = ""
    retrieved_at = ""
    if provenance.exists():
        prov = json.loads(provenance.read_text())
        source_url = prov.get("source_url", "")
        retrieved_at = prov.get("retrieved_at", "")
    parts.append(f"- **source_fixture:** `scouting/candidates/{benchmark_dir}/sample.parquet`")
    parts.append(f"- **source_url:** {source_url}")
    parts.append(f"- **retrieved_at:** `{retrieved_at}`")
    parts.append(f"- **price_table_pinned_at:** `{PRICE_TABLE_PINNED_AT}`")
    parts.append(f"- **cost_provenance:** `{cost_provenance_class}`")
    parts.append("")

    if cost_provenance_class == "as_reported_only":
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
                f"- {agent_id} — reported ${reported:.2f}, reconstructed ${recon:.2f} "
                f"(note: {note})"
            )
        parts.append("")
        parts.append("**Caveats:**\n")
        for c in cost_recon_data.get("caveats", []):
            parts.append(f"- {c}")
        parts.append("")

    # 3. Per-agent summary
    parts.append("## Per-agent summary\n")
    parts.append(
        "| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low "
        "| success_rate_ci_high | total_cost_usd | cost_per_success_usd |"
    )
    parts.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in result.per_agent:
        cps = (
            "inf" if s.cost_per_success_usd == float("inf")
            else _format_currency(s.cost_per_success_usd)
        )
        parts.append(
            f"| {s.agent_id} | {s.n_graded} | {s.n_errored} | "
            f"{_format_rate(s.success_rate)} | {_format_rate(s.success_rate_ci_low)} | "
            f"{_format_rate(s.success_rate_ci_high)} | "
            f"{_format_currency(s.total_cost_usd)} | {cps} |"
        )
    parts.append("")

    # 4. Claims
    parts.append("## Claims\n")
    target_mde = study.inference.target_mde
    if target_mde is not None:
        parts.append(
            "| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |"
        )
        parts.append("|---|---|---|---|---|---|---|")
    else:
        parts.append("| claim_id | mode | status | effect | adjusted_result | decision_impact |")
        parts.append("|---|---|---|---|---|---|")
    by_id = {s.agent_id: s for s in result.per_agent}
    mde_per_claim: list[tuple[str, float, float]] = []  # (claim_id, ci_half_width, target_mde)
    for c in result.claims:
        ci_crosses = c.delta_ci_low <= 0.0 <= c.delta_ci_high
        direction_matches = direction_matches_claim(
            study.primary_outcome.direction,
            c.delta_point_estimate,
        )
        ctx = ClaimContext(
            rejects_null=c.rejects_null,
            delta_point_estimate=c.delta_point_estimate,
            delta_ci_low=c.delta_ci_low,
            delta_ci_high=c.delta_ci_high,
            treatment_cost_usd=by_id[c.treatment].total_cost_usd,
            control_cost_usd=by_id[c.control].total_cost_usd,
            treatment_is_dominated=c.treatment not in result.pareto_frontier,
            direction_matches_claim=direction_matches,
        )
        di = decision_impact(ctx)
        status = _claim_status(c.rejects_null, direction_matches, ci_crosses)
        adj = "n/a" if c.adjusted_p_value is None else f"{c.adjusted_p_value:.4f}"
        row = {
            "claim_id": c.claim_id,
            "mode": study.analysis_mode,
            "status": status,
            "effect": _format_pp(c.delta_point_estimate),
            "adjusted_result": adj,
            "decision_impact": di,
        }
        if target_mde is not None:
            row["target_mde"] = _format_pp(target_mde)
            ci_half_width = (c.delta_ci_high - c.delta_ci_low) / 2.0
            mde_per_claim.append((c.claim_id, ci_half_width, target_mde))
        parts.append(render_claim_row(row))
    parts.append("")

    if target_mde is not None and mde_per_claim:
        parts.append("**MDE context**\n")
        for claim_id, half_width, mde in mde_per_claim:
            diff_pp = (half_width - mde) * 100
            if diff_pp < -0.5:
                wording = (
                    "the study has resolution finer than the declared MDE; "
                    "an effect of this size would be detectable"
                )
            elif abs(diff_pp) <= 0.5:
                wording = (
                    "the study sits at the declared MDE; "
                    "an effect of exactly this size sits on the detection boundary"
                )
            else:
                wording = (
                    "the study has resolution coarser than the declared MDE; "
                    "an effect at the declared MDE would not be reliably detected without more data"
                )
            parts.append(
                f"- `{claim_id}`: bootstrap CI half-width = {half_width * 100:.2f} pp "
                f"vs target_mde = {mde * 100:.2f} pp — {wording}."
            )
        parts.append("")

    # Verdict sensitivity sub-block (one per claim).
    from eval_audit.report.sensitivity import compute_sensitivity_rows

    for c in result.claims:
        rows = compute_sensitivity_rows(
            c,
            runs,
            study,
            result,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
        )
        baseline_verdict = rows[0].verdict
        parts.append(f"**Verdict sensitivity** — `{c.claim_id}`\n")
        parts.append("| dimension | value | verdict |")
        parts.append("|---|---|---|")
        for r in rows:
            verdict_cell = r.verdict
            if r.dimension != "baseline" and r.verdict != baseline_verdict:
                verdict_cell = f"{r.verdict} ← flips"
            parts.append(f"| {r.dimension} | {r.value} | {verdict_cell} |")
        parts.append("")

    # 5. Cost-quality view
    parts.append("## Cost-quality view\n")
    pareto_sorted = sorted(result.pareto_frontier)
    parts.append(f"**Pareto frontier (max success_rate, min total_cost_usd):** {pareto_sorted}")
    parts.append("")
    dominated = [s.agent_id for s in result.per_agent if s.agent_id not in result.pareto_frontier]
    if dominated:
        parts.append(
            f"Dominated agents: {sorted(dominated)}. Each is dominated by another agent that "
            "achieves at least the same success_rate at no greater total_cost_usd."
        )
    else:
        parts.append("All agents are on the frontier; no dominance to report.")
    parts.append("")

    # 6. Residual risks
    parts.append("## Residual risks\n")
    parts.append(
        "**Inherited from scouting decision** (verbatim from "
        f"`{decision_md_label}`):\n"
    )
    parts.append(_extract_residual_risks(decision_md, decision_md_label))
    parts.append("")

    # 7. Reproducibility footer
    parts.append("## Reproducibility footer\n")
    parts.append(f"- **rendered_at:** `{rendered_at}`")
    parts.append(f"- **git_commit:** `{git_commit}`")
    parts.append(f"- **fixture_sha256:** `{fixture_sha256}`")
    parts.append(f"- **bootstrap_seed:** `{result.bootstrap_seed}`")
    parts.append("")

    return "\n".join(parts)


def render_report_to(
    out_path: Path,
    study: StudySpec,
    runs: pl.DataFrame,
    *,
    clock: Callable[[], datetime],
    git_commit: str,
    fixture_sha256: str,
    repo_root: Path,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
) -> Path:
    """Run analyze() then render to disk. CrossHarnessComparisonError propagates
    BEFORE any file is written.
    """
    result = analyze(
        study,
        runs,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    text = render_report(
        result,
        study,
        runs,
        clock=clock,
        git_commit=git_commit,
        fixture_sha256=fixture_sha256,
        repo_root=repo_root,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return out_path
