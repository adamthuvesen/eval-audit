# eval-audit

[![CI](https://github.com/adamthuvesen/eval-audit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/adamthuvesen/eval-audit/actions/workflows/ci.yml)

**A model-selection audit toolkit for agent benchmarks.**

You read "Model X beats Model Y by 2 pp on benchmark Z." Should you switch
your default? `eval-audit` answers that with one of six verdicts —
`switch`, `hold`, `drop_from_shortlist`, `rerun_more_n`, `hedge_on_cost`,
`inconclusive_no_action` — each backed by paired-task bootstrap CIs,
multiple-comparison correction, Pareto cost-quality dominance, and a
robustness review that perturbs the inference choices to see whether the
verdict survives.

Concrete: Exhibit A reanalyzes Claude 3.7 Sonnet vs o4-mini High on 165
paired GAIA tasks under one harness. Claude is +1.82 pp on success rate
but costs 2.2× more, the paired bootstrap CI crosses zero, and the
verdict is:

```text
hedge_on_cost
```

A plausible leaderboard claim becomes a bounded, decision-relevant
statement. Three more rendered audits below cover the other verdict
shapes.

```bash
uv tool install eval-audit
eval-audit init my-first-audit && cd my-first-audit
eval-audit report study.yaml --runs runs.parquet --skip-validation
```

**Install** · [Five-minute walk-through](#first-audit-in-five-minutes) · [Browse rendered audits](#example-reports) · [CHANGELOG](CHANGELOG.md)

## What you'll see

Every report opens with a verdict, then proves it.

<!-- The Audit Summary and Robustness Review below are quoted verbatim from reports/exhibit-a/report.md. Update both together when the renderer changes. -->

### Audit summary

- **Verdict:** `hedge_on_cost` — The bootstrap CI for the delta crosses zero (no quality decision is available), but the cost gap is material (≥10% of the cheaper arm's cost). The decision pivots on cost preference rather than measured quality. Action: pick the cheaper arm unless the (statistically indistinguishable) quality difference matters to your use case.
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

Most benchmark write-ups stop at point estimates and pairwise comparisons.
That is enough for a blog post; it is not enough for a model-selection
decision you have to defend. The four common failure modes:

- pairwise comparisons reported without multiple-comparison correction
- point estimates without paired-task uncertainty
- cost treated as metadata or footnote, not as a first-class output
- verdicts that quietly assume the analyst's α / errored-row policy / correction is the only reasonable one

`eval-audit` is a small methodology toolkit for the better default:
*declare the claim, declare the analysis plan, analyze task-level data,
report only what survives uncertainty, correction, cost, and sensitivity
checks.*

## How it works

**Inputs.** A `StudySpec.yaml` declaring the claim, treatment/control
arms, outcome, α, target MDE, correction method, and cost view —
committed before outcomes are seen. Plus a canonical `RunRecord.parquet`
of task-level paired observations.

**Analysis.** Wilson intervals on per-arm success rates; paired-task
cluster bootstrap on deltas (task is the unit, not row); paired t-test
p-values; Holm-Bonferroni for declared confirmatory families,
Benjamini-Hochberg for exploratory families; Pareto frontier over
success-rate × total-cost; errored rows count as failures in the
headline denominator with `n_errored` surfaced separately; cost
provenance as a first-class field (`reconciled` if per-task cost
reconstruction matches reported totals, `as_reported_only` with a
visible report caveat if it does not).

**Outputs.** Deterministic markdown report with nine sections: Audit
Summary (verdict + rationale + what would change it), Study, Provenance,
Per-agent summary, Claims (with target MDE context), Verdict Sensitivity
(perturbations across α / errored-row policy / correction / cost
threshold), Robustness Review (survives / does-not-survive / caveat per
dimension), Cost-quality view (Pareto frontier + dominance), Residual
risks (inherited from scouting), and Reproducibility footer.
Snapshot-tested for byte-identity under fixed clock + git commit +
fixture sha + bootstrap seed.

**Refusals.** Cross-harness comparisons rejected at the schema gate.
Unsupported outcomes rejected. Unsupported correction methods rejected.
The methodology breaks if these slip through, so they don't.

**Adapters that ship today.** HAL GAIA, HAL TAU-bench Airline, a
synthetic known-truth fixture for stats-engine validation, and a
generic BYO loader for any canonical `RunRecord.parquet`.

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

## Controlled original-evidence audit

Exhibits A and B above are reanalyses of *public* HAL run records — useful for
showing what an audit looks like, but limited by what someone else already
shipped. The next category is different: a small, predeclared, *original* run
that we own end-to-end.

### Exhibit C: HumanEval (Claude Haiku 4.5 vs Claude Sonnet 4.6)

[reports/exhibit-c/report.md](reports/exhibit-c/report.md) is a
**controlled original-evidence** audit, not a reanalysis. The run design was
locked in [scouting/exhibit-c-decision.md](scouting/exhibit-c-decision.md)
and [scouting/exhibit-c/run-plan.md](scouting/exhibit-c/run-plan.md) before
any model call was made: 30 HumanEval tasks (sampled with seed=42),
`eval-audit/exhibit-c-direct-v1` thin direct-completion harness with no
tools, two reruns per (agent, task) at temperature=0, errored-row policy
inherited from v0.

Headline: Sonnet 60/60 (100%) vs Haiku 53/60 (88.3%) → +11.67 pp with
bootstrap CI [+1.67 pp, +23.33 pp]. Adjusted p = 0.0504 (just barely above
α=0.05) and the verdict is:

```text
inconclusive_no_action
```

The decision impact is honest about the resolution: a 30-task run can place
the effect's CI but not separate it from noise at the declared MDE. The
report's Verdict Sensitivity section shows the verdict flips to `switch` at
α=0.10, which is the kind of caveat an audit should make visible rather than
bury.

This is the only exhibit in the repo built from runs we authored ourselves,
and it is deliberately small. `eval-audit` is still not a benchmark runner;
Exhibit C is a single declared claim under one locked harness, committed
end-to-end so the methodology loop can be inspected from raw API responses
through to the rendered verdict.

## Example reports

The four committed reports exercise different decision verbs, evidence
modes, and provenance paths.

- [reports/exhibit-a/report.md](reports/exhibit-a/report.md) — verdict `hedge_on_cost`. Single-claim within-harness reanalysis (HAL Generalist on GAIA) with `reconciled` cost provenance.
- [reports/exhibit-b/report.md](reports/exhibit-b/report.md) — three pairwise claims producing two `hedge_on_cost` verdicts and one `drop_from_shortlist`. Exercises the `as_reported_only` cost-provenance path.
- [reports/exhibit-c/report.md](reports/exhibit-c/report.md) — verdict `inconclusive_no_action`. Controlled original-evidence audit on HumanEval (Haiku 4.5 vs Sonnet 4.6) with `reconciled` cost provenance and a predeclared run plan.
- [reports/byo-minimal/report.md](reports/byo-minimal/report.md) — synthetic worked example producing a `switch` verdict. Demonstrates the bring-your-own-data path end-to-end.

## Decision pattern gallery

The reports above cover three of the six decision verdicts on real or BYO data. The decision pattern gallery is a **synthetic** worked example that fills in the rest. It is not benchmark evidence — it exists only to demonstrate how each verdict renders end-to-end so a reader can see the verdict language alongside a real audit report.

The gallery covers `hold`, `rerun_more_n`, and `inconclusive_no_action`.

- [reports/decision-gallery/report.md](reports/decision-gallery/report.md) — rendered audit covering all three claims in one report.
- [examples/decision-gallery/README.md](examples/decision-gallery/README.md) — worked walkthrough explaining each claim's calibration and which decision rule it triggers.

## Bring your own data

`eval-audit` works on any task-level eval data shaped to the canonical
`RunRecord` contract. The fastest way in:

```bash
eval-audit init my-study               # scaffold ./my-study/{study.yaml,runs.parquet,make_runs.py,README.md}
# edit my-study/make_runs.py with your data, then:
python my-study/make_runs.py           # regenerate runs.parquet from inline data
eval-audit validate my-study/runs.parquet my-study/study.yaml
eval-audit analyze  my-study/study.yaml --runs my-study/runs.parquet
```

The scaffold round-trips out-of-the-box — `validate` and `analyze` succeed on
the toy data immediately after `init`, so you have a working example to
edit. See
[`examples/byo-minimal/README.md`](examples/byo-minimal/README.md) for the
worked walkthrough,
[`agents/docs/INPUT_CONTRACT.md`](agents/docs/INPUT_CONTRACT.md) for the
formal field-by-field `RunRecord` reference, and
[`agents/docs/STUDY_SCHEMA.md`](agents/docs/STUDY_SCHEMA.md) for the
formal field-by-field `StudySpec` reference.

## Install

`eval-audit` ships as a CLI tool. The fastest way in:

```bash
uv tool install eval-audit
```

Or, with `pipx`:

```bash
pipx install eval-audit
```

Both install paths put the `eval-audit` binary on your `PATH` and resolve
the version from package metadata, so `eval-audit --version` works without
a source checkout. See [CHANGELOG.md](CHANGELOG.md) for what's in the
current release.

## First audit in five minutes

From a fresh `uv tool install`, take a new BYO study from scaffold to
rendered audit report:

```bash
# 1. Install (one-time).
uv tool install eval-audit

# 2. Scaffold a new BYO study with toy data and study spec.
eval-audit init my-first-audit
cd my-first-audit

# 3. Pre-flight check: validate the runs parquet and study spec together.
eval-audit validate runs.parquet study.yaml

# 4. Run the analysis (writes reports/my-first-audit/analysis.json).
eval-audit analyze study.yaml --runs runs.parquet

# 5. Render the audit report.
#    --skip-validation bypasses the synthetic-validation pytest gate, which
#    is a development-time guardrail not bundled with the published wheel.
eval-audit report study.yaml --runs runs.parquet --skip-validation
```

The rendered report lands at `reports/my-first-audit/report.md`. Open it
to see the full nine sections — Audit Summary, Study, Provenance,
Per-agent summary, Claims, Robustness Review, Cost-quality view, Residual
risks, and Reproducibility footer — produced from the toy 2-agent 10-task
fixture. Edit `make_runs.py` (or replace `runs.parquet` with your own
canonical RunRecord parquet) to point the same audit machinery at your
data; see [`agents/docs/INPUT_CONTRACT.md`](agents/docs/INPUT_CONTRACT.md)
for the field-by-field `RunRecord` reference.

## Quickstart

For contributors and anyone working from a source checkout. Install
development dependencies:

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

Reproduce Exhibit C (controlled original-evidence audit) from the committed
canonical fixture — no API keys needed, the runs.parquet is committed:

```bash
uv run eval-audit spec validate studies/exhibit-c.yaml
uv run eval-audit validate examples/exhibit-c/runs.parquet studies/exhibit-c.yaml
uv run eval-audit analyze studies/exhibit-c.yaml --runs examples/exhibit-c/runs.parquet --bootstrap-iterations 8000 --bootstrap-seed 42
uv run eval-audit report  studies/exhibit-c.yaml --runs examples/exhibit-c/runs.parquet --bootstrap-iterations 8000 --bootstrap-seed 42
```

To regenerate Exhibit C from scratch (calls the Anthropic API; needs
`ANTHROPIC_API_KEY` in `.env.local`; estimated cost <\$1), see
[scouting/exhibit-c/README.md](scouting/exhibit-c/README.md).

Run the full local check:

```bash
make check
```

## Current v1 scope

`eval-audit` deliberately supports a narrow, honest contract: `success_rate` /
`higher_is_better` outcomes, task-level paired comparisons within one harness,
frequentist intervals and corrections, deterministic markdown reports. The
schema rejects anything outside this scope rather than silently coercing it.
See [Future work](#future-work) for the deferred extensions.

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
make test     # uv run pytest
make lint     # uv run ruff check .
make check    # both, the canonical local gate
```

CI runs `make check` on every push and pull request, on any branch.

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

Deferred until a concrete consumer asks (or a methodology need forces it):

- broaden supported outcomes beyond `success_rate` / `higher_is_better` —
  first candidates are `latency_s` and `cost_usd` as `lower_is_better`
- HTML / PDF report output (markdown stays canonical)
- more public-data adapters where fixture provenance is solid
- a second controlled exhibit on a different task source

See [CHANGELOG.md](CHANGELOG.md) for what shipped, and the demo reports
above for the current rendered output.
