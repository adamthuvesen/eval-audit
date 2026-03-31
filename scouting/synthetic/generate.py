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

Run:
    cd scouting/synthetic && python generate.py
"""

from __future__ import annotations

import json
import math
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


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def main() -> None:
    spec = yaml.safe_load(SPEC_PATH.read_text())
    rng = np.random.default_rng(spec["design"]["random_seed"])
    n_tasks = spec["design"]["n_tasks"]
    n_seeds = spec["design"]["n_seeds_per_task"]
    agents = spec["agents"]

    # Per-task difficulty (drawn once, shared across all agents).
    task_diff = rng.normal(
        loc=spec["noise_model"]["task_difficulty_logit_mean"],
        scale=spec["noise_model"]["task_difficulty_logit_sigma"],
        size=n_tasks,
    )
    # Per-(agent, task) interaction (drawn once, shared across seeds).
    interaction = rng.normal(
        0.0,
        spec["noise_model"]["agent_task_interaction_sigma"],
        size=(len(agents), n_tasks),
    )

    rows = []
    expected_p_per_agent = {}
    for ai, agent in enumerate(agents):
        skill = agent["skill_logit"]
        # Analytical expected success rate: mean over (task_diff + interaction noise).
        p_each_task = np.array([
            sigmoid(skill - task_diff[t] + interaction[ai, t])
            for t in range(n_tasks)
        ])
        expected_p_per_agent[agent["id"]] = float(p_each_task.mean())

        for t in range(n_tasks):
            p = sigmoid(skill - task_diff[t] + interaction[ai, t])
            for s in range(n_seeds):
                # Sample success from Bernoulli(p) using a fresh draw.
                success = int(rng.random() < p)
                # Token counts: log-normal around agent-typical scale.
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
    pq.write_table(table, RUNS_PATH)
    print(f"wrote {RUNS_PATH} ({RUNS_PATH.stat().st_size:,} bytes), {len(rows)} rows")

    # Compute observed per-agent success rates and cost.
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

    # Pairwise effect sizes (true).
    pairwise = []
    ids = [a["id"] for a in agents]
    for a, b in combinations(ids, 2):
        delta = observed[a]["expected_success_rate"] - observed[b]["expected_success_rate"]
        # Simple two-prop variance approx for "would Holm flag this" sanity.
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

    # Pareto frontier (max success, min cost).
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

    TRUTH_PATH.write_text(json.dumps(truth, indent=2) + "\n")
    print(f"wrote {TRUTH_PATH}")
    print(f"\nper-agent expected vs observed success rate:")
    for aid, o in observed.items():
        print(f"  {aid:<25} expected={o['expected_success_rate']:.3f}  observed={o['observed_success_rate']:.3f}  cost_mean=${o['observed_mean_cost_usd']:.4f}")
    print(f"\nPareto frontier (observed cost, expected success): {pareto}")
    print(f"primary pair pairwise effect: {[p for p in pairwise if set([p['agent_a'], p['agent_b']]) == set(spec['inference_targets']['primary_pair'])]}")


if __name__ == "__main__":
    main()
