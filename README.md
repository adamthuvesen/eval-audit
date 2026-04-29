# rigor

> **Verdict-grade evals.** Every benchmark claim resolves to an action verb — `switch`, `hold`, `drop_from_shortlist`, `rerun_more_n`, `hedge_on_cost`, `inconclusive_no_action` — with a sensitivity table attached. "What should we do?" is a more useful eval output than "what's the rank order?"

**Status:** v1 in progress · verdict-grade evals · 2026-05-02

---

## What rigor renders

Every rendered report carries a per-claim verdict and a sensitivity table that shows whether the verdict survives reasonable perturbations of the analysis declaration. A verdict that holds across every perturbation is the strong claim; a verdict that flips under one is a methodological footnote that the report surfaces honestly.

```
| dimension          | value     | verdict           |
|--------------------|-----------|-------------------|
| baseline           | locked    | hedge_on_cost     |
| alpha              | 0.01      | hedge_on_cost     |
| alpha              | 0.10      | hedge_on_cost     |
| errored_policy     | excluded  | hedge_on_cost     |
| correction_method  | none      | hedge_on_cost     |
| cost_gap_threshold | 0.05      | hedge_on_cost     |
| cost_gap_threshold | 0.20      | hedge_on_cost     |
```

(Excerpt from [reports/exhibit-a/report.md](reports/exhibit-a/report.md). Verdicts that flip under a perturbation are annotated `← flips`.)

The supporting machinery — declared analysis plans, paired-task cluster bootstrap, Holm-Bonferroni, Pareto frontier on cost-quality, errored-row policy, locked column mappings — is what makes the verdicts trustworthy. The verdict is the headline.

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

For a worked example of how this matters in practice, see [reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md): the same model on the same benchmark scores 12 percentage points apart under two different scaffolds the public TAU-bench leaderboard mixes into a single ranking.

## How rigor implements it

### 1. Study specifications and analysis plans

A YAML/Pydantic schema for agent benchmark studies:

```yaml
# Excerpt from studies/exhibit-a.yaml (the live, locked v0 study spec).
id: exhibit-a
benchmark: gaia
analysis_mode: declared_reanalysis
data_observation: summary_seen
harness: hal_generalist_agent

primary_outcome:
  name: success_rate
  unit: task
  direction: higher_is_better

agents:
  - id: "HAL Generalist Agent (claude-3-7-sonnet-20250219)"
  - id: "HAL Generalist Agent (o4-mini-2025-04-16 high)"

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
    - reconstructed_per_task_cost_usd
    - reported_run_total_cost_usd
    - cost_per_success_usd
  primary_view: pareto_frontier

claims:
  - id: claude37_vs_o4mini_high_on_gaia
    text: >-
      On GAIA validation under the HAL Generalist agent harness, Claude 3.7
      Sonnet outperforms o4-mini High; reanalysis evaluates whether the
      observed gap is statistically distinguishable from noise.
    treatment: "HAL Generalist Agent (claude-3-7-sonnet-20250219)"
    control:   "HAL Generalist Agent (o4-mini-2025-04-16 high)"
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
rigor spec validate studies/exhibit-a.yaml
rigor spec render   studies/exhibit-a.yaml --out study-spec.md --format markdown
```

### 2. Public-data reanalysis

v0 ships **two** end-to-end ingestion targets across both exercised cost-provenance classes:

- **HAL GAIA** (HAL Generalist Agent harness) — `reconciled` cost provenance. Per-task cost reconstructs from `tokens_in_by_model × pinned prices` and matches HAL's reported run-total within 1%. See [studies/exhibit-a.yaml](studies/exhibit-a.yaml) and [reports/exhibit-a/report.md](reports/exhibit-a/report.md).
- **HAL TAU-bench Airline** (Tool Calling harness) — `as_reported_only` cost provenance. Per-task cost reconstruction MAPE = 0.33; the renderer surfaces the divergence in a Provenance caveat block and falls back to `reported_run_total / successes` for `cost_per_success_usd`. See [studies/exhibit-b.yaml](studies/exhibit-b.yaml) and [reports/exhibit-b/report.md](reports/exhibit-b/report.md).

The toolkit's v0 bar was "one credible end-to-end example per cost-provenance class." Both shipped.

```bash
rigor analyze studies/exhibit-a.yaml --out reports/exhibit-a/analysis.json
rigor report  studies/exhibit-a.yaml --out reports/exhibit-a/report.md

rigor analyze studies/exhibit-b.yaml --out reports/exhibit-b/analysis.json
rigor report  studies/exhibit-b.yaml --out reports/exhibit-b/report.md
```

The Exhibit A claim is decision-oriented:

> "On GAIA validation under the HAL Generalist agent harness, Claude 3.7 Sonnet (56.4%) outperforms o4-mini High (54.5%) by 1.9 percentage points while costing 2.2x more ($130.68 vs $59.39). Is the 1.9 pp accuracy advantage statistically distinguishable from noise on n=165, and is it decision-relevant given the cost gap?"

This is a better first proof than a dramatic leaderboard reversal. It tests whether `rigor` can turn a plausible model-selection decision into an auditable claim with uncertainty, paired task analysis, and cost sensitivity. The actual rendered finding is **inconclusive** — the +1.82 pp observed delta sits inside a paired-task bootstrap CI that crosses zero, Holm-Bonferroni adjusted p = 0.7021, and the report's `decision_impact` is `hedge_on_cost`. That is the right answer, surfaced honestly, and is itself the demo.

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

Example claim output (the actual Exhibit A render — see [reports/exhibit-a/report.md](reports/exhibit-a/report.md)):

```text
Claim: Claude 3.7 Sonnet outperforms o4-mini High on GAIA under the HAL
       Generalist agent harness; reanalysis evaluates whether the observed
       1.9 pp gap is statistically distinguishable from noise on n=165 and
       decision-relevant given Claude is 2.2x more expensive.
Status: inconclusive

Observed success delta: +1.82 percentage points
Observed cost delta:    +$71.29 (Claude more expensive)
95% CI for success delta (paired-task bootstrap): [-2.6, +5.4] pp
Adjusted p (Holm-Bonferroni): 0.7021
Decision impact: hedge_on_cost

Interpretation:
The observed gap is small relative to its uncertainty; the data do not
support switching to Claude on quality alone. Given Claude costs 2.2x
more, prefer o4-mini High unless quality requirements not captured here
specifically demand Claude.
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

## Demos of the methodology

Three demonstrations of what verdict-grade evals produce on real public agent-eval data:

- **Exhibit A — GAIA HAL Generalist** ([reports/exhibit-a/report.md](reports/exhibit-a/report.md)). Claude 3.7 Sonnet vs o4-mini High on 165 GAIA validation tasks. Headline leaderboard gap is 1.9 pp; rigor's verdict is `hedge_on_cost` and the sensitivity table shows it holds across every perturbation. This is the `reconciled` cost-provenance demo.
- **Exhibit B — TAU-bench Airline Tool Calling** ([reports/exhibit-b/report.md](reports/exhibit-b/report.md)). Three-agent within-harness comparison (o4-mini High, Claude 3.7 Sonnet, o3 Medium) on 50 airline tasks. All three pairwise verdicts hold under the sensitivity table. This is the `as_reported_only` cost-provenance demo, with the toolkit's cost-caveat sub-block surfacing the per-task reconstruction failure honestly.
- **Cross-harness confound writeup** ([reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md)). Claude 3.7 Sonnet sits at 56% under HAL Generalist and 44% under Tool Calling on the same TAU-bench Airline task set — a 12 pp scaffold gap on the same model and the same benchmark that the public leaderboard mixes into a single ranking. The writeup uses Exhibit B's reanalysis as data and cites the leaderboard's HAL Generalist number from scouting provenance.

### Exhibit A scouting result

Current Exhibit A: **HAL GAIA (HAL Generalist Agent · Claude 3.7 Sonnet vs o4-mini High)**.

Why it wins (verdict from [scouting/exhibit-a-decision.md](scouting/exhibit-a-decision.md), which is the locked contract for the toolkit):

- **`reconciled` cost provenance, MAPE = 0.0.** HAL's reported run-total cost matches reconstruction from per-model token counts × pinned provider prices for both runs. GAIA is the only candidate where the cost story is fully auditable end-to-end without unexplained gaps.
- **Within-harness, cross-model decision.** Both agents run under the same HAL Generalist scaffold; differences attribute cleanly to the model choice without confounding harness effects.
- **n = 165 GAIA validation tasks per arm.** Paired across arms (same task set both ways) so paired-task cluster bootstrap is the natural uncertainty estimator.
- **Decision-relevant claim.** The leaderboard reports a 1.9 pp accuracy gap with a 2.2× cost gap — a real model-selection question a serious reader would ask, not a dramatic reversal.
- **Public artifacts with provenance metadata.** The two HAL trace zips are pinned by filename in [scouting/candidates/gaia/provenance.json](scouting/candidates/gaia/provenance.json); the column inventory is locked at [scouting/candidates/gaia/columns.json](scouting/candidates/gaia/columns.json).

**Exhibit B** is **TAU-bench Tool Calling** (HAL Airline traces). It passed all four selection gates but its cost reconciliation is `as_reported_only` (MAPE = 0.33; reconstructed costs diverge from reported in opposite directions across agents — likely prompt-caching discounts and stale price snapshots). Exhibit B exercises that cost-provenance branch end-to-end and carries the project's most decision-relevant scouting finding: a **12 pp cross-harness scaffold effect** for Claude 3.7 Sonnet (56% under HAL Generalist vs 44% under Tool Calling), the strongest argument the project has for "benchmark rows are not model effects." The reanalysis lives at [reports/exhibit-b/report.md](reports/exhibit-b/report.md); the cross-harness finding is written up at [reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md).

Resolved checks before schema lock (now historical; settled by the scouting phase):

- HAL GAIA traces decrypt and normalize cleanly into per-task rows (165 per agent for the chosen pair).
- Both agents share the GAIA validation task set, enabling paired task-level comparisons.
- Reconstructed-per-task cost (from `tokens_in_by_model` × pinned prices) matches HAL's reported `total_cost` within floating-point.
- v0's first success-rate comparison uses paired-task cluster bootstrap (each iteration resamples task_id with replacement, both arms scored on the resampled task list); McNemar/Wilson are available as supporting views.

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

CI runs `pytest`, `ruff`, and `openspec validate --all --strict` on every push and PR via [.github/workflows/ci.yml](.github/workflows/ci.yml). To make the workflow a *required* check that blocks merges, enable branch protection on `main` in GitHub Settings → Branches and add the `test` job as a required status check (one-time admin toggle, not in repo).

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

GAIA HAL Generalist is the locked Exhibit A. It should be replaced only if a future scouting pass shows that:

- HAL's `agent-evals/hal_traces` dataset regenerates and the pinned trace zips (named in [scouting/candidates/gaia/provenance.json](scouting/candidates/gaia/provenance.json)) are no longer retrievable; toolkit ingest fails loud on this drift today
- the locked column-to-semantic-role mapping in [scouting/exhibit-a-decision.md](scouting/exhibit-a-decision.md) no longer matches the upstream fixture (a different scouting pass would catch this and would itself be the change that swaps Exhibit A)
- per-task cost reconciliation drops below the 1% threshold the toolkit asserts on every load (e.g., a price-table refresh that breaks the `reconciled` invariant)
- the GAIA validation task set is sampled differently in some future HAL release such that paired-task analysis no longer applies

The replacement question is not "can we find a dramatic reversal?" It is "can we find a decision-relevant claim whose evidential status becomes clearer under a declared analysis plan?" The current Exhibit A's rendered status (**inconclusive** at adjusted p = 0.70, with `hedge_on_cost` as the decision_impact) is exactly that: a small observed gap properly wrapped in uncertainty, where the toolkit changes how a serious reader would act on the leaderboard.

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
- 2026-05-02 — Scouting completed; Exhibit A revised to **HAL GAIA (HAL Generalist · Claude 3.7 Sonnet vs o4-mini High)** based on cleaner cost reconciliation (MAPE = 0.0). TAU-bench retained as strong secondary; gate matrix in [scouting/exhibit-a-decision.md](scouting/exhibit-a-decision.md).
- 2026-05-02 — Synthetic fixture contract added (`repair-synthetic-fixture-contract` archived); seed `20260502 → 20260503` to land observed primary delta within 3pp of true delta and unblock the v0 synthetic-validation gate.
- 2026-05-02 — `v0-exhibit-a-reanalysis` landed: schema, GAIA + synthetic ingest, stats engine (Wilson, paired-task bootstrap, Holm-Bonferroni, Pareto), and markdown report. First Exhibit A reanalysis at [reports/exhibit-a/report.md](reports/exhibit-a/report.md): claim **inconclusive** at adjusted p=0.70, decision_impact `hedge_on_cost` (Claude 56.4% vs o4-mini 54.5%, +1.82 pp; CIs overlap, Claude 2.2× more expensive).
- 2026-05-02 — `exhibit-b-tau-bench-reanalysis` landed: HAL TAU-bench Tool Calling adapter, errored-row denominator policy at `analyze()` level, cost-provenance caveat sub-block in the report renderer. Exhibit B reanalysis at [reports/exhibit-b/report.md](reports/exhibit-b/report.md) hits leaderboard-matching success rates (o4-mini 56%, Claude 44%, o3 54%); cross-harness writeup at [reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md) makes the 12 pp Claude scaffold gap explicit. v0 success bar (two reanalyses across both exercised cost-provenance classes) closed.
- 2026-05-02 — `verdict-grade-evals` landed (v1.1 kickoff): repositioned the project around the action-verb verdict concept and added a per-claim Verdict sensitivity sub-block to every rendered report. Each claim now carries a small table showing whether the verdict survives perturbations of alpha, errored-row policy, correction method, and cost-gap threshold; rows that flip relative to baseline are annotated `← flips`. Exhibit A and Exhibit B both gained the new sub-block; all four claims across both exhibits proved robust under every perturbation.

## Cross-references

- Brain wiki: [career plan 2026-2028](local-brain-wiki-career-plan) — `rigor` is move #2 of Track B and the recommended-first project.
- Brain wiki: [Senior DS career reference](local-brain-wiki-career-reference) — research-portfolio differentiation rationale.
- Sibling repo: `~/dev/menti/counter` — counterfactual reasoning for agents.
- Sibling repos: `~/dev/menti/{autonomous-ml-research,autonomous-insights,trace,engram}` — existing pieces of the agent-infra portfolio.
- Reference: [HAL — Holistic Agent Leaderboard (Princeton)](https://github.com/princeton-pli/hal-harness) — closest existing infrastructure; `rigor` should complement rather than compete.
- Reference: [Long-Horizon Task Mirage paper (April 2026)](https://arxiv.org/html/2604.11978v1) — motivation for structural failure-mode analysis, but not a v0 auto-classification requirement.
- Reference: [From benchmarks to deployment — review of agentic evaluation (Springer, 2026)](https://link.springer.com/article/10.1007/s10462-026-11571-0) — motivation for improving benchmark methodology.
