# rigor

> Study-specification, reanalysis, and reporting toolkit for agent benchmarks. Treat agent evals like experiments, not score tables.

**Status:** v0 spec · Exhibit A selected · 2026-05-02

---

## The pitch

`rigor` helps researchers and practitioners make agent benchmark claims auditable. It provides:

- a study-specification schema for declaring evaluation plans and benchmark claims
- a reanalysis pipeline for public or private run-level benchmark data
- statistical reporting that separates robust findings from leaderboard noise
- cost-quality analysis that makes tradeoffs explicit instead of hiding them in a single rank

The v0 is deliberately narrow: **study specifications + HAL/public-data reanalysis + polished report**. It is not a new benchmark runner, not a leaderboard, and not a pile of adapters.

## Why this exists

Most agent benchmark reporting still looks more like a scoreboard than an experiment. Common failure modes:

- point estimates without uncertainty intervals
- many pairwise model comparisons without multiple-comparison correction
- binary success rates that hide task/category-level variation
- unclear seed strategies, stopping rules, and rerun policies
- cost reported as metadata rather than analyzed as part of the decision
- claims stated more strongly than the observed data supports

The opportunity is not to dunk on benchmark authors. The opportunity is to give the field a better default workflow:

> Declare the claim, declare the analysis plan, analyze run-level data, report what survives uncertainty and correction.

That is the agent-eval equivalent of bringing A/B-test discipline to a field that is still mostly publishing leaderboards.

## What v0 is

### 1. Study specifications and analysis plans

A YAML/Pydantic schema for agent benchmark studies:

```yaml
study:
  id: taubench-airline-frontier-2026-05
  benchmark: taubench_airline
  analysis_mode: declared_reanalysis
  data_observation: summary_seen

primary_outcome:
  name: success_rate
  unit: task
  direction: higher_is_better

agents:
  - id: taubench_toolcalling_o4mini_high
  - id: hal_generalist_claude37_sonnet
  - id: taubench_toolcalling_o3_medium

design:
  task_sampling: fixed_public_validation_set
  run_strategy: observed_public_runs
  observed_runs_per_agent: 1
  rerun_policy: recommend_if_decision_sensitive

inference:
  alpha: 0.05
  correction_method: holm_bonferroni
  comparison_family: declared_claims
  target_mde: 0.03

cost:
  metrics:
    - leaderboard_total_usd
    - trace_total_usd
    - usd_per_attempt
    - usd_per_success
    - wall_clock_seconds
  primary_view: pareto_frontier

claims:
  - id: o4mini_high_preferred_to_claude37
    text: "o4-mini High is preferred to Claude 3.7 Sonnet for TAU-bench Airline deployment under equal observed success and lower cost."
    treatment: taubench_toolcalling_o4mini_high
    control: hal_generalist_claude37_sonnet
    outcome: success_rate
```

Pre-registration is one use mode, not the name for every analysis. `rigor` should make the distinction explicit:

| Mode | Use when | Report wording |
|---|---|---|
| `preregistered` | The analysis plan was written before the analyst saw the relevant data. | "This confirmatory analysis was preregistered before data observation." |
| `declared_reanalysis` | The analysis plan was written for existing data, with some prior knowledge of the result source. | "This reanalysis plan was declared after data collection and may be post hoc." |
| `exploratory` | The goal is discovery, diagnosis, or hypothesis generation. | "These findings are exploratory and should not be treated as confirmatory." |

The CLI should validate the file and render a clean study-spec document:

```bash
rigor spec validate study.yaml
rigor spec render study.yaml --out study-spec.html
```

### 2. Public-data reanalysis

v0 starts with one ingestion target: **HAL TAU-bench Airline**. The first goal is not broad adapter coverage; it is one credible end-to-end example.

```bash
rigor ingest hal --benchmark taubench_airline --out runs.parquet
rigor analyze study.yaml runs.parquet --out analysis.json
rigor report analysis.json --out report.html
```

The Exhibit A claim is decision-oriented:

> "On TAU-bench Airline, TAU-bench Tool Calling with o4-mini High and HAL Generalist with Claude 3.7 Sonnet both show 56% observed accuracy, but o4-mini High costs substantially less. Should a benchmark consumer treat o4-mini High as the preferred deployment choice, or rerun before switching?"

This is a better first proof than a dramatic leaderboard reversal. It tests whether `rigor` can turn a plausible model-selection decision into an auditable claim with uncertainty, paired task analysis, and cost sensitivity.

The reanalysis should answer:

- What claim was tested?
- Was it preregistered, declared reanalysis, or exploratory?
- How much of the data had been observed before the plan was declared?
- What effect size was the study powered to detect?
- Which comparisons survive correction?
- Which conclusions are sensitive to seed/task resampling?
- Which agents are Pareto-dominated on quality and cost?
- What claims are unsupported by the observed data?
- Are leaderboard costs, trace-level costs, and configurable token-pricing costs being compared on the same basis?

### 3. Honest benchmark reports

The report is the product surface. It should be good enough to attach to a workshop paper, an internal model-selection memo, or a benchmark pull request.

Example claim output:

```text
Claim: o4-mini High is preferred to Claude 3.7 Sonnet for TAU-bench Airline deployment under equal observed success and lower cost.
Status: inconclusive

Observed success delta: 0.0 percentage points
Observed cost delta: -$30.75
95% CI for success delta: [-19.2, +19.2]
Decision impact: rerun_more_n

Interpretation:
The observed success rates are tied and o4-mini High is cheaper, but one
public run per agent is not enough to treat the deployment preference as a
confirmatory quality claim. Prefer o4-mini High only if the decision is
primarily cost-constrained; otherwise rerun before switching.
```

That framing is intentionally non-adversarial. It challenges overclaiming without making the project a gotcha machine.

Real reports should handle many claims at once. The top-level report view should look more like an A/B platform decision table than a paper appendix:

| Claim | Mode | Status | Effect | Adjusted result | Decision impact |
|---|---|---|---|---|---|
| Agent A beats Agent B | declared reanalysis | unsupported | +2.4 pp | p_adj = 0.18 | Do not switch on quality alone |
| Agent C is Pareto-dominated | exploratory | supported | lower quality, higher cost | dominated in 91% of bootstraps | Remove from shortlist |
| Agent A is cheaper per success | declared reanalysis | inconclusive | -$0.42 | CI crosses zero | Re-run with larger N |

`decision_impact` should be a controlled vocabulary, not arbitrary prose. Start small: `switch`, `hold`, `drop_from_shortlist`, `rerun_more_n`, `hedge_on_cost`, and `inconclusive_no_action`.

## Non-goals for v0

- No new benchmark runner.
- No six-benchmark adapter layer.
- No new leaderboard.
- No auto-classification of failure modes.
- No default composite score with hidden value judgments.
- No simultaneous Bayesian and frequentist analysis stacks.

These are tempting because they sound big. They are also how a two-week methodology project becomes an eighteen-week infrastructure treadmill.

## Methodology defaults

v0 should use a boring, defensible frequentist toolkit because that is what most benchmark readers already understand:

- Wilson or Agresti-Coull intervals for binary success rates
- bootstrap intervals for derived metrics where closed forms are awkward
- Holm-Bonferroni for confirmatory pairwise comparisons
- Benjamini-Hochberg for explicitly exploratory families
- pilot-conditioned MDE alongside upfront target-MDE planning
- task/category stratification when the underlying data supports it
- Pareto frontier as the primary cost-quality view

Bayesian hierarchical modeling is valuable, but it belongs in v1 after the schema and reporting workflow are trusted.

## Package shape

```text
rigor/
  schema/      StudySpec, RunRecord, AnalysisPlan, Claim
  spec/        validation, templates, HTML/PDF rendering
  ingest/      HAL/public-data importer
  stats/       intervals, MDE, correction, Pareto, sensitivity
  report/      HTML/Markdown report generation
  cli.py       init, spec, ingest, analyze, report
```

Likely dependencies:

- `pydantic` for schemas and validation
- `polars` for run-level data
- `scipy` and `statsmodels` for statistical methods
- `plotly` for report charts
- `jinja2` for HTML rendering

Deliberate non-dependencies:

- no benchmark harness framework
- no vector database
- no model-based trace classifier
- no custom agent runner

## Exhibit A scouting result

Current choice: **HAL TAU-bench Airline**.

Why it wins:

- compact benchmark: 50 public-test tasks
- public leaderboard with verified results, costs, run counts, and encrypted trace downloads
- public traces decrypt into task-level rewards, successful/failed task lists, per-task latencies, token usage, total cost, and run metadata
- decision-relevant frontier: o4-mini High matches Claude 3.7 Sonnet at 56% observed accuracy while costing much less
- methodologically relevant context: HAL removed TAU-bench Few Shot results due to data leakage, so the example naturally fits an evidence-quality story without becoming adversarial

Use **GAIA** as Exhibit B after the first importer/report works. GAIA is higher-profile and has level stratification, but it is noisier and less constrained for the first proof.

Open checks before schema lock:

- decrypt and normalize at least three TAU-bench Airline traces: o4-mini High, Claude 3.7 Sonnet, and o3 Medium
- confirm whether every candidate shares the same 50 tasks, enabling paired task-level comparisons
- reconcile leaderboard displayed cost with trace-level `total_cost` and configurable token-pricing calculations
- decide whether v0's first success-rate comparison should use independent intervals, paired tests, or both

## Reusable scouting protocol

Schema design should follow real datasets, not precede them. For future Exhibit B/C candidates:

1. Inspect HAL plus two alternates, likely Terminal-Bench logs and BrowseComp-style public results.
2. Export or scrape the smallest useful run-level/table-level sample from each.
3. Inventory the actual columns: agent, model, task, category, seed/run id, success, cost, tokens, latency, trace reference, and rerun metadata.
4. Check whether cost per attempt and cost per success are directly available or reconstructible.
5. Identify one concrete model-selection claim that a serious reader might make from the original report.
6. Pick the candidate only if the resulting report would clarify a real decision.

If no public benchmark satisfies the criteria, v0 should not stall. Plan B is:

- build a synthetic known-ground-truth study to demonstrate that the statistical machinery behaves correctly
- pair it with the best available real reanalysis, even if the real case is messier or less dramatic
- consider reaching out to HAL early if richer run-level data would make the collaboration useful to both sides

The synthetic case proves the method. The real case proves relevance.

## Testing approach

A stats library earns trust through tests, not just API polish. v0 should include:

- fixture tests on hand-computed tiny datasets
- property-based tests for multiple-comparison correction invariants
- cross-checks against `statsmodels`, `scipy`, or R reference outputs for intervals and p-values
- snapshot tests for report text so claim wording does not drift into overstatement

## v0 success criteria

v0 is successful when the repo can:

1. Validate and render a study-spec file.
2. Ingest one real public benchmark result source.
3. Produce a report with uncertainty intervals, corrected comparisons, MDE context, and cost-quality plots.
4. Evaluate at least one explicit benchmark claim as supported, unsupported, or inconclusive.
5. Publish one polished example reanalysis that changes how a serious reader would make or trust a model-selection decision.

The bar is not "many adapters." The bar is "one report that changes how a serious reader thinks about benchmark evidence."

## v1+ ideas

- More public-data importers once v0 proves useful.
- Mixed-effects or hierarchical models for task/category/benchmark structure.
- Bayesian reanalysis mode with credible intervals and partial pooling.
- Sequential testing / always-valid inference for expensive reruns.
- Failure-mode taxonomy support as a human-labeled schema field.
- Failure-mode auto-classification only after measuring inter-rater reliability.
- Shadow reports for widely cited benchmark claims.
- Integration with `counter` for causal attribution of agent failures.

## Positioning

Bad launch story:

> "We show that a famous benchmark result is not statistically significant."

Better launch story:

> "We show how agent benchmark conclusions change when evaluations use declared analysis plans, cost-aware reporting, uncertainty intervals, and multiple-comparison controls."

The first is politically brittle. The second is useful, durable, and much harder to dismiss.

## Open questions

### What would disqualify Exhibit A?

TAU-bench Airline is the current bet. It should be replaced only if the next sampling pass shows that:

- trace schemas differ too much across runs to normalize cleanly
- agents do not share a comparable fixed task set
- cost provenance cannot be explained without guesswork
- the first report would merely restate the leaderboard instead of changing decision confidence

The replacement question is not "can we find a dramatic reversal?" It is "can we find a decision-relevant claim whose evidential status becomes clearer under a declared analysis plan?"

### Who is v0 for?

The README originally implied three audiences at once:

- practitioners who want a library
- academics who want a paper
- labs/journalists who want a leaderboard

The four-to-six-week version can serve one primary audience. The current bet: **researchers and serious practitioners who want auditable benchmark claims**. The library and paper fall out of that; the leaderboard can wait.

## Why this compounds

| Compound with | How |
|---|---|
| **counter** | `counter` produces causal hypotheses about agent failures; `rigor` evaluates whether the evidence supports them. |
| **Confidence at Menti** | Product experimentation discipline maps directly onto benchmark design and claim validation. |
| **Autonomous ML Research** | Existing experiment workflows need the same study-specification, MDE, and reporting discipline. |
| **HAL / Princeton's leaderboard** | HAL is strong infrastructure; `rigor` can complement it with claim-level inference and declared analysis plans. |

## Decision log

- 2026-05-02 — repo created. Initial brain dump focused on an experimental-rigor harness for agent benchmarks.
- 2026-05-02 — v0 reframed around study specifications, public-data reanalysis, and honest reports. Broad benchmark adapters moved out of v0.
- 2026-05-02 — terminology tightened: core artifact is a study specification; strict pre-registration is one analysis mode, distinct from declared reanalysis and exploratory work.
- 2026-05-02 — Exhibit A selected: HAL TAU-bench Airline, focused on cost-aware model selection along the frontier.

## Cross-references

- Brain wiki: [career plan 2026-2028](local-brain-wiki-career-plan) — `rigor` is move #2 of Track B and the recommended-first project.
- Brain wiki: [Senior DS career reference](local-brain-wiki-career-reference) — research-portfolio differentiation rationale.
- Sibling repo: `~/dev/menti/counter` — counterfactual reasoning for agents.
- Sibling repos: `~/dev/menti/{autonomous-ml-research,autonomous-insights,trace,engram}` — existing pieces of the agent-infra portfolio.
- Reference: [HAL — Holistic Agent Leaderboard (Princeton)](https://github.com/princeton-pli/hal-harness) — closest existing infrastructure; `rigor` should complement rather than compete.
- Reference: [Long-Horizon Task Mirage paper (April 2026)](https://arxiv.org/html/2604.11978v1) — motivation for structural failure-mode analysis, but not a v0 auto-classification requirement.
- Reference: [From benchmarks to deployment — review of agentic evaluation (Springer, 2026)](https://link.springer.com/article/10.1007/s10462-026-11571-0) — motivation for improving benchmark methodology.
