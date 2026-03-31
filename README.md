# rigor

> Experimental-rigor harness for agent benchmarking. Proper randomization, MDE-aware sample sizing, multi-comparison correction, cost-efficiency in the primary score. The A/B-test mindset applied to agent eval.

**Status:** brain dump · v0 design phase · 2026-05-02

---

## The pitch in one paragraph

`rigor` is a Python package that wraps existing agent benchmarks (Terminal-Bench, OSWorld, BrowseComp, HumanEval, AutoResearchBench, etc.) and replaces their statistical methodology with something a causal-inference person wouldn't be embarrassed by: proper randomization across seeds and configs, minimum-detectable-effect-aware sample-size guidance, multi-comparison correction when comparing N agents, cost-per-success and quality-cost-pareto reporting in the primary score, and a structural failure-mode taxonomy beyond binary success. The launch story: take one widely-cited benchmark result and show it isn't statistically significant under proper analysis.

## Why this exists

### The methodology gap

A 2026 review of 15 major agent benchmarks (Springer, *Artificial Intelligence Review*) found:

- **0/15** integrate safety or security into scoring
- **0/15** include cost-efficiency in their primary evaluation protocol
- **13/15** rely *exclusively* on binary success measures

Princeton's HAL leaderboard partially fixes this (token-cost tracking, reproducibility), but it doesn't address the deeper statistical-methodology gap: most benchmark papers report point estimates with no confidence intervals, no multi-comparison adjustment, and treat comparisons of N agents as if they're N independent two-sample tests. The "Long-Horizon Task Mirage" paper (April 2026) demonstrated that long-horizon failure modes are **structural shifts in failure composition**, not just lower success rates — meaning the binary-success scoring everyone uses is *actively misleading*.

### The differentiation

Almost everyone running agent benchmarks treats them as software-engineering reproducibility problems. The combination of **(deep experimentation/A-B-testing background) × (causal-inference instincts) × (production agentic systems experience)** is genuinely rare. `rigor` is the project that converts that combination into a public artifact.

This is also The project's most natural research-portfolio piece: it leans hardest into existing skills, has the lowest novelty-of-method risk, and can plausibly be a workshop paper at NeurIPS 2026 / ICLR 2027 ("Methodological audit of agent benchmarks: power, MDE, and multi-comparison failures across 15 widely-cited evaluations").

## v0 scope (4–6 weeks of evening/weekend work)

A Python package that:

1. **Wraps existing benchmark harnesses** — provides adapters for Terminal-Bench 2.0, OSWorld-Verified, BrowseComp, HumanEval, AutoResearchBench, and HAL. Each adapter exposes a standardized `BenchmarkRun` object.
2. **Adds proper randomization** — multi-seed runs by default, with seed-stratified analysis. Detects when results aren't seed-stable.
3. **Computes MDE / required-N upfront** — given a target effect size and significance level, tells the user how many runs they need *before* they spend $10K running them.
4. **Multi-comparison correction** — when comparing N agents, defaults to Holm-Bonferroni or Benjamini-Hochberg. Flags reports that don't apply correction.
5. **Cost-efficiency in primary score** — every metric reported alongside cost (tokens, $, wall-clock). Default reporting is a quality × cost Pareto frontier.
6. **Failure-mode taxonomy** — not just success/fail, but a structural breakdown: planning errors, memory errors, tool errors, hallucination errors, refusal errors, timeout errors. Per the Long-Horizon Task Mirage paper.
7. **Publishes one reproduced result** with a finding: "[widely-cited benchmark X] reports method A is 4.2 points better than method B; under proper multi-seed analysis with multi-comparison correction, this difference is not statistically significant."

API sketch:

```python
import rigor

# Define what we're testing
study = rigor.Study(
    benchmark="terminal-bench-2.0",
    agents=["claude-opus-4-7", "gpt-5-5", "gemini-3-pro"],
    n_seeds=20,
    target_mde=0.03,  # detect 3-percentage-point differences
    alpha=0.05,
    cost_weight=0.3,  # 30% weight on cost in composite score
)

# Power analysis before spending money
plan = study.power_analysis()
print(plan.required_n_per_arm)  # → 47 runs per agent
print(plan.estimated_cost_usd)  # → $1,240

# Run it (or import previously-run data)
results = study.run()  # or study.load("results.json")

# Get the report — with confidence intervals, MC correction, Pareto plot
report = results.report()
report.to_html("agent-comparison-2026-05.html")

# The honest summary
print(report.honest_summary())
# → "Under multi-seed (n=20) analysis with Holm-Bonferroni correction (α=0.05),
#    no pairwise difference between the three agents is statistically significant
#    on success rate. claude-opus-4-7 dominates on the cost-quality Pareto frontier."
```

## v1+ stretch goals

- **Bayesian re-analysis** of public benchmark results — pull HAL leaderboard data, redo the analysis with proper hierarchical models, publish a "shadow leaderboard" with credible intervals.
- **Failure-mode taxonomy auto-classification** — fine-tune a small model (or use Claude Haiku) to classify failure traces into the structural taxonomy. Currently most papers eyeball this.
- **Sequential testing / early stopping** — bring proper sequential analysis (mSPRT, Always Valid Inference) to expensive agent benchmarks. Save 50%+ of compute.
- **Integration with `counter`** — when failures cluster around a specific decision, counter can attribute the failure to that decision causally.
- **A paper.** Title sketch: *"Methodological audit of LLM-agent benchmarks: a power and multi-comparison analysis of 15 widely-cited evaluations."* Submission target: NeurIPS 2026 Workshop on Foundation Model Evaluation.

## Technical approach (rough)

Three layers:

1. **Adapter layer.** One adapter per benchmark, normalizing their output into a standard `Result` schema (run_id, agent_id, seed, success, sub-tasks, latency_s, tokens_in, tokens_out, cost_usd, failure_mode, full_trace_ref).
2. **Statistics layer.** A small set of well-tested functions: `power_analysis`, `apply_mc_correction`, `bootstrap_ci`, `pareto_frontier`, `failure_mode_distribution`. No reinventing — built on `scipy.stats`, `statsmodels`, `pingouin`.
3. **Reporting layer.** A clean HTML report (`jinja2` + `plotly`) that no one will be embarrassed to share. Markdown export for academic papers.

Likely dependencies:
- `pydantic` for the standardized Result schema
- `polars` for results data
- `scipy.stats` + `statsmodels` for the methodology
- `pingouin` for clean stats API
- `plotly` for the Pareto plot
- `jinja2` for the HTML report

Likely **non**-dependencies (deliberate):
- No new agent runner — wrap existing harnesses, don't reimplement
- No new benchmark — the value is methodology, not benchmark design
- No vector DB / embedding magic — pure tabular stats

## Why this compounds with the rest

| Compound with | How |
|---|---|
| **counter** (sibling project) | counter's interventional predictions need rigorous evaluation. rigor evaluates them. |
| **Product experimentation practice** | Product experimentation uses controlled tests for product decisions. rigor brings the same mindset to agent eval. |
| **Autonomous ML Research** | This repo already runs ML experiments; rigor's methodology is what should be running underneath. |
| **HAL / Princeton's leaderboard** | rigor can publish a "shadow leaderboard" using HAL's raw data with proper statistics. Friendly co-existence. |

## What labs would care about (the elevator pitch)

> *"Almost every published agent benchmark reports point estimates without confidence intervals, no multi-comparison correction, no cost-efficiency in the primary score, and binary success measures that miss structural failure-mode shifts in long-horizon tasks. We built a methodology layer that fixes this and ran it against the top 15 benchmarks. Several widely-cited results don't survive proper analysis. The library is OSS; the audit is a paper."*

That sentence works in a cold DM to anyone at Anthropic Evals, OpenAI Evals, GDM evaluation teams, or the AISI / METR / Apollo Research orbit.

## Open questions / risks

- **Reproducibility friction.** Re-running benchmarks costs real money. v0 should focus on benchmarks where pre-computed result tables exist (HAL has these), so we can do reanalysis without rerunning. Re-running is v1+.
- **Political risk.** Showing that widely-cited results don't survive proper analysis will annoy the authors. Frame the project as collaborative ("here's how to get more out of your benchmark") not adversarial. The audit paper should name methodology, not authors.
- **Methodology drift.** Some benchmarks are *deliberately* binary or single-seed because that's what the underlying task supports. v0 should avoid bashing those — focus on the cases where authors *could* have done more rigorous analysis and didn't.

## Decision log

- 2026-05-02 — repo created. Brain dump v0 from chat with the wiki agent.

## Cross-references

- Brain wiki: [career plan 2026–2028](local-brain-wiki-career-plan) — rigor is move #2 of Track B and the recommended-first project.
- Brain wiki: [Senior DS career reference](local-brain-wiki-career-reference) — research-portfolio differentiation rationale.
- Sibling repo: `counter` — counterfactual reasoning for agents (causal lens; rigor is the eval lens).
- Sibling repos: `autonomous-ml-research, autonomous-insights, trace, and engram` — existing pieces of the agent-infra portfolio.
- Reference: [HAL — Holistic Agent Leaderboard (Princeton)](https://github.com/princeton-pli/hal-harness) — the closest existing infrastructure; rigor complements rather than competes.
- Reference: [Long-Horizon Task Mirage paper (April 2026)](https://arxiv.org/html/2604.11978v1) — primary motivation for the structural failure-mode taxonomy.
- Reference: [From benchmarks to deployment — review of agentic evaluation (Springer, 2026)](https://link.springer.com/article/10.1007/s10462-026-11571-0) — primary source for the 0/15-cost-efficiency, 13/15-binary-success findings.
