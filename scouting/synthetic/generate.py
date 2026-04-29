"""Generate scouting/synthetic/runs.parquet and truth.json from spec.yaml.

Deterministic given spec.yaml. Re-running with the same spec produces the
same outputs (modulo Parquet writer metadata). The dataset is intentionally
small (~1,200 rows: 4 agents x 60 tasks x 5 seeds) so the toolkit can run
end-to-end on it in a fraction of a second.

The "truth" file records what the reanalysis pipeline SHOULD recover:
  - per-agent expected success rate (analytical)
  - per-agent expected cost
  - all pairwise true effect sizes
  - whether each pair is "really" different at alpha=0.05 in expectation
  - Pareto-frontier membership

Per `repair-synthetic-fixture-contract`, this script enforces realization
acceptance criteria from `spec.yaml`'s `acceptance_criteria:` block. If any
criterion fails, the canonical files are NOT updated and the script exits
non-zero. Use `--check-only` to evaluate criteria against a tempdir without
touching canonical paths (used by `find_seed.py`).

Run:
    cd scouting/synthetic && python generate.py
    cd scouting/synthetic && python generate.py --check-only
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from itertools import combinations
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).parent
SPEC_PATH    = ROOT / "spec.yaml"
RUNS_PATH    = ROOT / "runs.parquet"
TRUTH_PATH   = ROOT / "truth.json"

REQUIRED_CRITERIA_KEYS = (
    "primary_delta_tolerance_pp",
    "per_agent_rate_tolerance_pp",
    "bootstrap_iterations",
    "bootstrap_seed",
    "alpha",
)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _load_spec() -> dict:
    spec = yaml.safe_load(SPEC_PATH.read_text())
    criteria = spec.get("acceptance_criteria") or {}
    missing = [k for k in REQUIRED_CRITERIA_KEYS if k not in criteria]
    if missing:
        sys.stderr.write(
            f"spec.yaml is missing required acceptance_criteria keys: {missing}\n"
            "Add the block per `repair-synthetic-fixture-contract` design.\n"
        )
        sys.exit(2)
    return spec


def _generate_to(spec: dict, runs_path: Path, truth_path: Path) -> tuple[list[dict], dict]:
    """Run generation against arbitrary output paths; return (rows, truth dict)."""
    rng = np.random.default_rng(spec["design"]["random_seed"])
    n_tasks = spec["design"]["n_tasks"]
    n_seeds = spec["design"]["n_seeds_per_task"]
    agents = spec["agents"]

    task_diff = rng.normal(
        loc=spec["noise_model"]["task_difficulty_logit_mean"],
        scale=spec["noise_model"]["task_difficulty_logit_sigma"],
        size=n_tasks,
    )
    interaction = rng.normal(
        0.0,
        spec["noise_model"]["agent_task_interaction_sigma"],
        size=(len(agents), n_tasks),
    )

    rows = []
    expected_p_per_agent = {}
    for ai, agent in enumerate(agents):
        skill = agent["skill_logit"]
        p_each_task = np.array([
            sigmoid(skill - task_diff[t] + interaction[ai, t])
            for t in range(n_tasks)
        ])
        expected_p_per_agent[agent["id"]] = float(p_each_task.mean())

        for t in range(n_tasks):
            p = sigmoid(skill - task_diff[t] + interaction[ai, t])
            for s in range(n_seeds):
                success = int(rng.random() < p)
                in_tokens = max(1, int(rng.lognormal(
                    mean=math.log(agent["typical_input_tokens_mean"]),
                    sigma=agent["typical_input_tokens_sigma"],
                )))
                out_tokens = max(1, int(rng.lognormal(
                    mean=math.log(agent["typical_output_tokens_mean"]),
                    sigma=agent["typical_output_tokens_sigma"],
                )))
                cost_usd = (
                    in_tokens  * agent["cost_per_1m_input"]  / 1_000_000
                  + out_tokens * agent["cost_per_1m_output"] / 1_000_000
                )
                latency = rng.lognormal(
                    mean=math.log(spec["noise_model"]["base_latency_seconds_mean"]),
                    sigma=spec["noise_model"]["base_latency_seconds_sigma"],
                )
                rows.append({
                    "agent_id":      agent["id"],
                    "task_id":       f"task_{t:03d}",
                    "seed":          s,
                    "success":       success,
                    "cost_usd":      round(cost_usd, 6),
                    "tokens_in":     in_tokens,
                    "tokens_out":    out_tokens,
                    "wall_clock_s":  round(latency, 4),
                })

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, runs_path)

    observed = {}
    for agent in agents:
        agent_rows = [r for r in rows if r["agent_id"] == agent["id"]]
        observed[agent["id"]] = {
            "tasks":            len({r["task_id"] for r in agent_rows}),
            "n_observations":   len(agent_rows),
            "observed_success_rate":     sum(r["success"] for r in agent_rows) / len(agent_rows),
            "expected_success_rate":     expected_p_per_agent[agent["id"]],
            "observed_mean_cost_usd":    sum(r["cost_usd"] for r in agent_rows) / len(agent_rows),
            "observed_mean_tokens_in":   sum(r["tokens_in"] for r in agent_rows) / len(agent_rows),
            "observed_mean_tokens_out":  sum(r["tokens_out"] for r in agent_rows) / len(agent_rows),
            "observed_mean_latency_s":   sum(r["wall_clock_s"] for r in agent_rows) / len(agent_rows),
        }

    pairwise = []
    ids = [a["id"] for a in agents]
    for a, b in combinations(ids, 2):
        delta = observed[a]["expected_success_rate"] - observed[b]["expected_success_rate"]
        n_per_arm = n_tasks * n_seeds
        pa_, pb_ = observed[a]["expected_success_rate"], observed[b]["expected_success_rate"]
        se = math.sqrt(pa_ * (1 - pa_) / n_per_arm + pb_ * (1 - pb_) / n_per_arm)
        z  = abs(delta) / se if se > 0 else 0.0
        pairwise.append({
            "agent_a":         a,
            "agent_b":         b,
            "true_delta":      round(delta, 4),
            "approx_z":        round(z, 3),
            "approx_unadjusted_p": round(2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))), 6),
            "n_per_arm":       n_per_arm,
        })

    pareto = []
    for a in agents:
        a_acc  = observed[a["id"]]["expected_success_rate"]
        a_cost = observed[a["id"]]["observed_mean_cost_usd"]
        dominated = False
        for b in agents:
            if a["id"] == b["id"]:
                continue
            b_acc  = observed[b["id"]]["expected_success_rate"]
            b_cost = observed[b["id"]]["observed_mean_cost_usd"]
            if b_acc >= a_acc and b_cost <= a_cost and (b_acc > a_acc or b_cost < a_cost):
                dominated = True
                break
        if not dominated:
            pareto.append(a["id"])

    truth = {
        "study_id":            spec["study"]["id"],
        "spec_path":           str(SPEC_PATH.relative_to(ROOT.parent.parent)),
        "n_agents":            len(agents),
        "n_tasks":             n_tasks,
        "n_seeds_per_task":    n_seeds,
        "n_observations":      len(rows),
        "agents":              observed,
        "pairwise_true_effects": pairwise,
        "pareto_frontier":     pareto,
        "expected_pareto_per_spec": spec["inference_targets"]["expected_pareto_membership"],
        "expected_holm_bonferroni_significant": spec["inference_targets"]["expected_holm_bonferroni_significant"],
        "primary_pair":        spec["inference_targets"]["primary_pair"],
        "alpha":               spec["inference_targets"]["alpha"],
    }

    truth_path.write_text(json.dumps(truth, indent=2) + "\n")
    return rows, truth


# --- Acceptance criteria checks --------------------------------------------------


def _check_primary_delta_proximity(spec: dict, truth: dict) -> tuple[bool, str]:
    primary = spec["inference_targets"]["primary_pair"]
    a_id, b_id = primary[0], primary[1]
    a, b = truth["agents"][a_id], truth["agents"][b_id]
    observed_delta = a["observed_success_rate"] - b["observed_success_rate"]
    true_delta = a["expected_success_rate"] - b["expected_success_rate"]
    tol = spec["acceptance_criteria"]["primary_delta_tolerance_pp"] / 100.0
    diff = abs(observed_delta - true_delta)
    if diff <= tol:
        return True, (
            f"primary_delta_proximity OK: observed={observed_delta:+.4f} "
            f"true={true_delta:+.4f} |diff|={diff:.4f} <= tol={tol:.4f}"
        )
    return False, (
        f"primary_delta_proximity FAILED: observed={observed_delta:+.4f} "
        f"true={true_delta:+.4f} |diff|={diff:.4f} > tol={tol:.4f}"
    )


def _check_primary_bootstrap_ci_crosses_zero(
    spec: dict,
    rows: list[dict],
) -> tuple[bool, str]:
    primary = spec["inference_targets"]["primary_pair"]
    crit = spec["acceptance_criteria"]
    a_id, b_id = primary[0], primary[1]

    a_rows = [r for r in rows if r["agent_id"] == a_id]
    b_rows = [r for r in rows if r["agent_id"] == b_id]

    a_by_task: dict[str, list[int]] = {}
    b_by_task: dict[str, list[int]] = {}
    for r in a_rows:
        a_by_task.setdefault(r["task_id"], []).append(r["success"])
    for r in b_rows:
        b_by_task.setdefault(r["task_id"], []).append(r["success"])

    shared_tasks = sorted(set(a_by_task) & set(b_by_task))
    a_means = np.array([float(np.mean(a_by_task[t])) for t in shared_tasks])
    b_means = np.array([float(np.mean(b_by_task[t])) for t in shared_tasks])

    rng = np.random.default_rng(crit["bootstrap_seed"])
    n = len(shared_tasks)
    n_iter = int(crit["bootstrap_iterations"])
    indices = rng.integers(0, n, size=(n_iter, n))
    deltas = a_means[indices].mean(axis=1) - b_means[indices].mean(axis=1)
    alpha = float(crit["alpha"])
    lo = float(np.quantile(deltas, alpha / 2))
    hi = float(np.quantile(deltas, 1 - alpha / 2))

    if lo <= 0.0 <= hi:
        return True, (
            f"primary_bootstrap_ci_crosses_zero OK: 95% CI=[{lo:+.4f}, {hi:+.4f}] contains 0"
        )
    return False, (
        f"primary_bootstrap_ci_crosses_zero FAILED: "
        f"95% CI=[{lo:+.4f}, {hi:+.4f}] excludes 0 (n_iter={n_iter}, seed={crit['bootstrap_seed']})"
    )


def _check_pareto_membership_match(spec: dict, truth: dict) -> tuple[bool, str]:
    expected = set(spec["inference_targets"]["expected_pareto_membership"])
    realized = set(truth["pareto_frontier"])
    if expected == realized:
        return True, f"pareto_membership_match OK: {sorted(realized)}"
    missing = expected - realized
    extra = realized - expected
    return False, (
        f"pareto_membership_match FAILED: "
        f"expected={sorted(expected)} realized={sorted(realized)} "
        f"missing={sorted(missing)} extra={sorted(extra)}"
    )


def _check_per_agent_rate_proximity(spec: dict, truth: dict) -> tuple[bool, str]:
    tol = spec["acceptance_criteria"]["per_agent_rate_tolerance_pp"] / 100.0
    failures: list[str] = []
    for agent_id, a in truth["agents"].items():
        diff = abs(a["observed_success_rate"] - a["expected_success_rate"])
        if diff > tol:
            failures.append(
                f"{agent_id}: observed={a['observed_success_rate']:.4f} "
                f"expected={a['expected_success_rate']:.4f} |diff|={diff:.4f} > tol={tol:.4f}"
            )
    if not failures:
        return True, f"per_agent_rate_proximity OK: all agents within {tol:.4f}"
    return False, "per_agent_rate_proximity FAILED: " + "; ".join(failures)


def _evaluate_criteria(
    spec: dict,
    rows: list[dict],
    truth: dict,
) -> list[tuple[str, bool, str]]:
    return [
        ("primary_delta_proximity", *_check_primary_delta_proximity(spec, truth)),
        ("primary_bootstrap_ci_crosses_zero", *_check_primary_bootstrap_ci_crosses_zero(spec, rows)),
        ("pareto_membership_match", *_check_pareto_membership_match(spec, truth)),
        ("per_agent_rate_proximity", *_check_per_agent_rate_proximity(spec, truth)),
    ]


# --- CLI -------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--check-only",
        action="store_true",
        help="generate to a tempdir, evaluate criteria, print results, do NOT touch canonical paths.",
    )
    return p.parse_args()


def run(check_only: bool = False) -> int:
    """Generate, evaluate criteria, optionally promote to canonical paths.

    Returns the process exit code (0 on success).
    """
    spec = _load_spec()
    with tempfile.TemporaryDirectory(prefix="rigor-synthetic-") as tmp:
        tmp_runs = Path(tmp) / "runs.parquet"
        tmp_truth = Path(tmp) / "truth.json"
        rows, truth = _generate_to(spec, tmp_runs, tmp_truth)
        results = _evaluate_criteria(spec, rows, truth)

        all_ok = all(ok for _, ok, _ in results)
        for _name, ok, msg in results:
            marker = "PASS" if ok else "FAIL"
            print(f"[{marker}] {msg}")

        if not all_ok:
            failing = [name for name, ok, _ in results if not ok]
            sys.stderr.write(
                f"\nGeneration aborted: {len(failing)} acceptance criteria failed: {failing}\n"
                f"Canonical files at {RUNS_PATH} and {TRUTH_PATH} are unchanged.\n"
                "Run scouting/synthetic/find_seed.py to find a seed that satisfies all criteria.\n"
            )
            return 1

        if check_only:
            print("\n--check-only: criteria pass; canonical files NOT touched.")
            return 0

        os.replace(tmp_runs, RUNS_PATH)
        os.replace(tmp_truth, TRUTH_PATH)
        print(f"\nwrote {RUNS_PATH} ({RUNS_PATH.stat().st_size:,} bytes), {len(rows)} rows")
        print(f"wrote {TRUTH_PATH}")
        print("\nper-agent expected vs observed success rate:")
        for aid, o in truth["agents"].items():
            print(
                f"  {aid:<25} expected={o['expected_success_rate']:.3f}  "
                f"observed={o['observed_success_rate']:.3f}  "
                f"cost_mean=${o['observed_mean_cost_usd']:.4f}"
            )
        print(f"\nPareto frontier (observed cost, expected success): {truth['pareto_frontier']}")
        primary = spec["inference_targets"]["primary_pair"]
        primary_pe = [
            p for p in truth["pairwise_true_effects"]
            if {p["agent_a"], p["agent_b"]} == set(primary)
        ]
        print(f"primary pair pairwise effect: {primary_pe}")
        return 0


def main() -> None:
    args = _parse_args()
    sys.exit(run(check_only=args.check_only))


if __name__ == "__main__":
    main()
