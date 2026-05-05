# eval-audit

**Verdict-grade evals for agent benchmarks.**

`eval-audit` turns benchmark claims into auditable decisions. Instead of stopping at
a leaderboard rank, it asks:

- What claim is being tested?
- What analysis plan was declared?
- Does the effect survive uncertainty and multiple-comparison correction?
- Does the answer change when cost or errored-row policy changes?
- What should a model selector actually do?

The report output is intentionally action-shaped: `switch`, `hold`,
`drop_from_shortlist`, `rerun_more_n`, `hedge_on_cost`, or
`inconclusive_no_action`.

## What you'll see

Every report opens with a verdict, then proves it.

<!-- The Audit Summary and Robustness Review below are quoted verbatim from reports/exhibit-a/report.md. Update both together when the renderer changes. -->

### Audit summary

- **Verdict:** `hedge_on_cost` — CI crosses zero and the cost gap is material
- **Claim status:** inconclusive
- **Why:** delta +1.82 pp with bootstrap CI [-7.27 pp, +10.91 pp] over 165 paired tasks; treatment is 2.20x the control's cost
- **What would change it:** ~1351 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** 5 residual risks inherited from scouting

### Robustness review

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 9.09 pp > MDE 3.00 pp; under-resolved |
| Cost provenance | survives | reconciled |

See [reports/exhibit-a/report.md](reports/exhibit-a/report.md) for the full report (Study, Provenance, Per-agent summary, Claims, Verdict sensitivity, Cost-quality view, Residual risks, Reproducibility footer).

## Why this exists

Agent benchmark reporting often looks like a scoreboard: point estimates, vague
run policies, uncorrected pairwise comparisons, and cost treated as metadata.
That is too weak for model-selection decisions.

`eval-audit` is a small methodology toolkit for a better default:

> Declare the claim, declare the analysis plan, analyze task-level data, and
> report only what survives uncertainty, correction, cost, and sensitivity
> checks.

## What ships

- Pydantic/YAML study specs with strict v0 validation.
- Canonical task-level `RunRecord` validation.
- Public-data ingest adapters for:
  - HAL GAIA
  - HAL TAU-bench Airline
  - a synthetic known-truth fixture
- Paired-task cluster bootstrap for success-rate deltas.
- Wilson intervals for binary success rates.
- Holm-Bonferroni and Benjamini-Hochberg correction.
- Cost-quality Pareto frontier.
- Cost provenance handling:
  - `reconciled` when per-task reconstruction matches reported totals
  - `as_reported_only` with a visible report caveat when it does not
- Deterministic markdown reports with verdict sensitivity tables.
- CI for tests and linting.

## Demo reports

### Exhibit A: GAIA HAL Generalist

[reports/exhibit-a/report.md](reports/exhibit-a/report.md) reanalyzes Claude
3.7 Sonnet vs o4-mini High on 165 paired GAIA validation tasks under the same
HAL Generalist harness.

Headline: Claude is +1.82 pp on success rate but costs 2.2x more. The paired
bootstrap CI crosses zero, Holm-Bonferroni adjusted p = 0.7021, and the
decision impact is:

```text
hedge_on_cost
```

That is the point of the project: a plausible leaderboard claim becomes a
bounded, decision-relevant statement.

### Exhibit B: TAU-bench Airline Tool Calling

[reports/exhibit-b/report.md](reports/exhibit-b/report.md) reanalyzes three
agents on TAU-bench Airline under the Tool Calling harness. It exercises the
`as_reported_only` cost-provenance path: per-task token reconstruction does not
reconcile to HAL's reported totals, so the report surfaces the caveat instead
of pretending the cost basis is cleaner than it is.

### Cross-harness confound

[reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md)
documents the strongest scouting finding: Claude 3.7 Sonnet scores 56% under
HAL Generalist and 44% under Tool Calling on TAU-bench Airline. The same model
on the same benchmark shifts by 12 pp across scaffolds, which is exactly why
benchmark rows should not be read as pure model effects.

## Quickstart

Install dependencies:

```bash
uv sync --extra dev
```

Validate a study spec:

```bash
uv run eval-audit spec validate studies/exhibit-a.yaml
```

Render a study-spec document:

```bash
uv run eval-audit spec render studies/exhibit-a.yaml --out /tmp/exhibit-a-spec.md
```

Run analysis:

```bash
uv run eval-audit analyze studies/exhibit-a.yaml
uv run eval-audit analyze studies/exhibit-b.yaml
```

Render reports:

```bash
uv run eval-audit report studies/exhibit-a.yaml
uv run eval-audit report studies/exhibit-b.yaml
```

Run the full local check:

```bash
make check
```

## Current v0 scope

`eval-audit` deliberately supports a narrow, honest v0 contract:

- primary outcome: `success_rate`
- direction: `higher_is_better`
- task-level paired comparisons within one harness
- frequentist intervals/corrections
- markdown reports

The schema now rejects unsupported outcomes instead of accepting declarations
that the engine would silently analyze as success rate. Broader outcomes such
as latency, cost, partial credit, or lower-is-better metrics should be added
only with metric-specific inference and report semantics.

## Methodology

For success-rate studies, `eval-audit` uses:

- audit summary front-loaded as the first section: verdict, claim status, why,
  what would change it, reviewer pushback
- resolution planning: target_mde + bootstrap CI half-width → required N
  estimate (variance-fixed scaling)
- robustness review: per-claim survives/does-not-survive/caveat table across
  multiple-comparison correction, errored-row policy, cost-threshold
  sensitivity, target MDE, and cost provenance
- errored rows counted as failures in the headline denominator, with
  `n_errored` still surfaced separately
- paired-task cluster bootstrap for delta uncertainty
- paired task-level p-values
- Holm-Bonferroni for declared confirmatory claim families
- Benjamini-Hochberg for exploratory claim families
- Pareto frontier over success rate and total cost
- verdict sensitivity over alpha, correction method, errored-row policy, and
  cost-gap threshold

## Repository map

```text
eval_audit/
  schema/      StudySpec and RunRecord models
  ingest/      benchmark fixture adapters
  stats/       intervals, bootstrap, correction, analysis, Pareto
  report/      markdown report rendering and decision rules
  spec/        study-spec rendering
  cli.py       Typer CLI

studies/       declared study specs
reports/       rendered demo reports and notes
scouting/      fixture provenance and candidate analysis
tests/         unit, property, fixture, snapshot, and validation tests
```

## Development

```bash
make test
make lint
make check
```

CI runs pytest and ruff on pushes and PRs to `main`.

## What is intentionally not here

- No benchmark runner.
- No leaderboard.
- No composite score with hidden weights.
- No model-based trace classifier.
- No cross-harness causal attribution.
- No Bayesian/hierarchical model yet.

Those are useful directions, but the current project is about making a small
number of benchmark claims defensible end to end.

## Future work

Methodological extensions worth taking on, in rough priority order:

- richer outcome support beyond binary success rate
- run-to-run replication support when benchmark traces expose seeds
- HTML/PDF report output
- more public benchmark adapters after the first two examples prove the shape

v1 shipped the audit-summary header, resolution planning, and robustness
review sections; see the demo reports above for the rendered output.
