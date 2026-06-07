"""Regenerate examples/decision-gallery/runs.parquet from inline data.

The decision-gallery is a SYNTHETIC pattern-demonstration study, not benchmark
evidence. The data is constructed so each claim renders a specific decision
verdict end-to-end. After writing the parquet, this script runs the analysis
pipeline against the gallery study and asserts that each claim's verdict
matches the calibration target. Drift fails the script.

Usage:

    python examples/decision-gallery/make_runs.py

The committed runs.parquet must round-trip from this script.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Calibration constants — change with care; see the per-claim comments below.
#
# Each claim's verdict depends on:
#   - The treatment's Pareto-frontier position (computed across ALL agents).
#   - The paired-task t-test raw p-value.
#   - The Holm-Bonferroni adjusted p across the three-claim family.
#   - The bootstrap CI's relationship to zero.
#
# Pareto-frontier coupling is the most fragile dimension. The cost values
# below are tuned so each treatment is non-dominated in the per-agent summary.
# ---------------------------------------------------------------------------

HARNESS = "decision-gallery"
TASKS_PER_AGENT = 10

# `hold_pattern` claim: treatment significantly underperforms control with
# clean per-task differences (no offsetting wins). Costs put hold_treatment
# strictly cheaper than hold_control so it is not Pareto-dominated.
# Per-task pairing (10 tasks): both succeed=2, treatment-only=0, control-only=7,
# both fail=1 → 7 −1 differences and 3 zeros → mean −0.7, low variance, p≈0.001.
# Verdict path: rejects_null=True, direction_matches_claim=False → `hold`.
HOLD_TREATMENT_SUCCESS = [True, True, False, False, False, False, False, False, False, False]
HOLD_CONTROL_SUCCESS = [True, True, True, True, True, True, True, True, True, False]
HOLD_TREATMENT_COST = 0.02  # per task; 10 tasks → $0.20 total. Cheapest agent.
HOLD_CONTROL_COST = 0.05  # per task; 10 tasks → $0.50 total. Highest-success agent.

# `rerun_more_n_pattern` claim: tied per-arm success rates with offsetting
# per-task wins/losses so the bootstrap CI clearly straddles zero. Costs
# differ by ~6.67% of the cheaper arm, below the 10% material threshold.
# Per-task pairing: both succeed=3, treatment-only=2, control-only=2,
# both fail=3 → 2 +1s, 2 −1s, 6 zeros → mean 0, t=0, p=1.0.
# Verdict path: not dominated, not rejected, CI crosses zero, cost gap < 10%
# → `rerun_more_n`.
RERUN_TREATMENT_SUCCESS = [True, True, True, True, True, False, False, True, False, False]
RERUN_CONTROL_SUCCESS = [True, True, True, False, False, True, True, False, False, False]
RERUN_TREATMENT_COST = 0.030  # per task; 10 tasks → $0.30 total.
RERUN_CONTROL_COST = 0.032  # per task; 10 tasks → $0.32 total. Gap ~6.67%.

# `inconclusive_no_action_pattern` claim: the CI/p disagreement case. Per-task
# differences are entirely +1 or 0 (no negatives), so the bootstrap percentile
# CI is entirely positive. The raw t-test p-value sits in the 0.025–0.05
# range, where Holm-Bonferroni adjustment across the three-claim family
# pushes the adjusted p above α=0.05.
# Per-task pairing: both succeed=4, treatment-only=4, control-only=0,
# both fail=2 → 4 +1s, 6 zeros → mean +0.4, t≈2.58, raw p≈0.030.
# Holm step 2: adjusted_p = max(3*p_hold, 2*0.030) ≈ 0.060 > 0.05 → not rejected.
# Verdict path: not dominated, not rejected, CI does NOT cross zero, no cost
# rule → `inconclusive_no_action`.
INCONC_TREATMENT_SUCCESS = [True, True, True, True, True, True, True, True, False, False]
INCONC_CONTROL_SUCCESS = [True, True, True, True, False, False, False, False, False, False]
INCONC_TREATMENT_COST = 0.04  # per task; 10 tasks → $0.40 total. Cheaper than hold_control.
INCONC_CONTROL_COST = 0.06  # per task; 10 tasks → $0.60 total.


_AGENT_BLOCKS: tuple[tuple[str, list[bool], float], ...] = (
    ("hold_treatment", HOLD_TREATMENT_SUCCESS, HOLD_TREATMENT_COST),
    ("hold_control", HOLD_CONTROL_SUCCESS, HOLD_CONTROL_COST),
    ("rerun_treatment", RERUN_TREATMENT_SUCCESS, RERUN_TREATMENT_COST),
    ("rerun_control", RERUN_CONTROL_SUCCESS, RERUN_CONTROL_COST),
    ("inconc_treatment", INCONC_TREATMENT_SUCCESS, INCONC_TREATMENT_COST),
    ("inconc_control", INCONC_CONTROL_SUCCESS, INCONC_CONTROL_COST),
)

_CLAIM_TARGETS: dict[str, str] = {
    "hold_pattern": "hold",
    "rerun_more_n_pattern": "rerun_more_n",
    "inconclusive_no_action_pattern": "inconclusive_no_action",
}


def _row(
    *,
    agent_id: str,
    task_id: str,
    success: bool,
    cost: float,
) -> dict:
    return {
        "agent_id": agent_id,
        "model_id": agent_id,
        "harness": HARNESS,
        "run_id": f"run-{agent_id}",
        "task_id": task_id,
        "task_category": None,
        "seed": 0,
        "success": success,
        "partial_credit": float(success),
        "outcome_status": "graded",
        "tokens_in": 1000,
        "tokens_out": 200,
        "tokens_in_by_model": {agent_id: 1000},
        "tokens_out_by_model": {agent_id: 200},
        "latency_s": 1.0,
        "timestamp": None,
        "reconstructed_per_task_cost_usd": cost,
        "reported_run_total_cost_usd": cost * TASKS_PER_AGENT,
        "cost_provenance": "reconciled",
        "rerun_metadata": {"source": "examples/decision-gallery"},
    }


def build_frame() -> pl.DataFrame:
    rows: list[dict] = []
    for agent_id, successes, cost in _AGENT_BLOCKS:
        if len(successes) != TASKS_PER_AGENT:
            raise ValueError(
                f"agent {agent_id!r} has {len(successes)} successes; expected {TASKS_PER_AGENT}"
            )
        for i, success in enumerate(successes, start=1):
            rows.append(
                _row(
                    agent_id=agent_id,
                    task_id=f"task_{i:02d}",
                    success=success,
                    cost=cost,
                )
            )
    return pl.DataFrame(rows, strict=False)


def _assert_calibration(parquet_path: Path) -> None:
    """Run the analysis pipeline and assert each claim's verdict matches the target.

    Imports are local so the script's basic write-parquet path stays import-light.
    """
    from eval_audit.ingest.generic import load_run_records
    from eval_audit.report.decisions import (
        ClaimContext,
        decision_impact,
        direction_matches_claim,
    )
    from eval_audit.schema import StudySpec
    from eval_audit.stats import analyze
    from eval_audit.stats.pareto import pareto_frontier

    repo_root = Path(__file__).resolve().parent.parent.parent
    study = StudySpec.from_yaml(repo_root / "studies" / "decision-gallery.yaml")
    runs = load_run_records(parquet_path)
    result = analyze(study, runs, bootstrap_iterations=10_000, bootstrap_seed=42)

    # Recompute the Pareto frontier so we can mirror the renderer's
    # treatment_is_dominated check per claim.
    per_agent_frame = pl.DataFrame(
        {
            "agent_id": [s.agent_id for s in result.per_agent],
            "success_rate": [s.success_rate for s in result.per_agent],
            "cost": [s.total_cost_usd for s in result.per_agent],
        }
    )
    frontier = set(pareto_frontier(per_agent_frame, success_col="success_rate", cost_col="cost"))
    cost_by_agent = {s.agent_id: s.total_cost_usd for s in result.per_agent}

    failures: list[str] = []
    for claim, claim_result in zip(study.claims, result.claims, strict=True):
        target = _CLAIM_TARGETS[claim.id]
        ctx = ClaimContext(
            rejects_null=claim_result.rejects_null,
            delta_point_estimate=claim_result.delta_point_estimate,
            delta_ci_low=claim_result.delta_ci_low,
            delta_ci_high=claim_result.delta_ci_high,
            treatment_cost_usd=cost_by_agent[claim.treatment],
            control_cost_usd=cost_by_agent[claim.control],
            treatment_is_dominated=claim.treatment not in frontier,
            direction_matches_claim=direction_matches_claim(
                study.primary_outcome.direction, claim_result.delta_point_estimate
            ),
        )
        actual = decision_impact(ctx)
        if actual != target:
            failures.append(
                f"  - claim {claim.id!r}: targeted {target!r}, got {actual!r}\n"
                f"    delta={claim_result.delta_point_estimate:+.4f} "
                f"CI=[{claim_result.delta_ci_low:+.4f}, {claim_result.delta_ci_high:+.4f}] "
                f"raw_p={claim_result.raw_p_value:.4f} "
                f"adj_p={claim_result.adjusted_p_value:.4f} "
                f"rejects_null={claim_result.rejects_null} "
                f"treatment_dominated={claim.treatment not in frontier}"
            )

    if failures:
        msg = (
            "decision-gallery calibration failed: at least one claim's verdict "
            "drifted from the calibration target. Re-tune the synthetic data in "
            "make_runs.py.\n" + "\n".join(failures)
        )
        raise SystemExit(msg)


def main() -> None:
    frame = build_frame()
    out_path = Path(__file__).resolve().parent / "runs.parquet"
    frame.write_parquet(out_path)
    print(f"wrote {out_path} ({frame.height} rows)")
    _assert_calibration(out_path)
    print("calibration: all 3 claims render their target verdicts")


if __name__ == "__main__":
    main()
