# eval-audit

`eval-audit` audits a benchmark comparison you have already run and answers one
question:

> Is the claim that Model B beats Model A large, reliable, and cost-aware
> enough to act on?

You give it a declared study (the comparison, the outcome metric, the claims),
paired per-task outcomes, and inference/cost settings. It returns a
deterministic Markdown report with a single decision verb per claim.

It does not run benchmarks, score leaderboards, or explain trace-level
failures. It audits evidence that already exists.

## How it works

The unit of analysis is the **task**, not the row, because two agents run on the
same task set and the per-task outcomes are paired. Given that:

- **Effect size and uncertainty** come from a paired-task cluster bootstrap:
  resample `task_id`s with replacement (seeded), recompute the delta of mean
  outcomes each time, and take percentiles of the resampled deltas as the
  confidence interval. Per-agent success rates carry Wilson score intervals.
- **Multiple comparisons** within a declared claim family are corrected —
  Holm-Bonferroni (step-down) for family-wise error, or Benjamini-Hochberg for
  FDR. The decision uses the adjusted p-value, never the raw one.
- **Resolution** is checked against a declared target MDE: a comparison whose
  bootstrap CI is wider than the effect it claims to detect is flagged as
  under-resolved rather than reported as a null result.
- **Cost** enters as a Pareto frontier over (success rate, cost) plus explicit
  cost provenance. When per-task cost cannot be reconstructed honestly from the
  source artifacts, cost-based verdicts are suppressed rather than fabricated.

A deterministic decision rule maps that evidence to one of six verdicts. Same
inputs in, same report out — snapshot-tested.

| Verdict | Meaning |
| --- | --- |
| `switch` | Treatment is better enough to choose. |
| `hold` | Control remains the better choice. |
| `drop_from_shortlist` | Treatment is dominated on cost-quality. |
| `rerun_more_n` | Evidence is under-resolved; collect more paired tasks. |
| `hedge_on_cost` | Quality is unclear, so cost should drive the choice. |
| `inconclusive_no_action` | The audit does not support a change. |

Alongside `report.md`, a completed audit writes `summary.json` — a deterministic
machine-readable claim summary the portfolio/index views read.

## Scope

Current scope is intentionally narrow: `success_rate`, `higher_is_better`,
paired task-level comparisons within **one** harness, frequentist
intervals/corrections, cost provenance, and Markdown reports. Cross-harness
comparisons are refused as confounded, not papered over — see
[reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md).

## Install

```bash
uv tool install eval-audit   # or: pipx install eval-audit
eval-audit --version
```

## Inputs

Two files describe an audit:

- `study.yaml` — benchmark/task family, harness, agents, outcome, claims,
  inference settings, and cost view.
- `runs.parquet` — one row per agent-task observation, with `agent_id`,
  `harness`, `task_id`, `success`, `outcome_status`, token/cost fields, and
  `cost_provenance`.

## Quickstart

Run the no-secret BYO demo from this repo:

```bash
uv run eval-audit audit examples/byo-minimal/study.yaml \
  --runs examples/byo-minimal/runs.parquet \
  --out-dir /tmp/eval-audit-reports \
  --html
```

Expected artifacts:

```text
/tmp/eval-audit-reports/byo-minimal/check.json
/tmp/eval-audit-reports/byo-minimal/analysis.json
/tmp/eval-audit-reports/byo-minimal/report.md
/tmp/eval-audit-reports/byo-minimal/report.html
/tmp/eval-audit-reports/byo-minimal/summary.json
```

The committed preview is
[reports/byo-minimal/report.md](reports/byo-minimal/report.md). Key lines:

```text
## Audit Summary

- Verdict: switch
- Claim status: supported
- Why: delta +40.00 pp with bootstrap CI [+10.00 pp, +70.00 pp] over 10 paired tasks; treatment is 2.00x the control's cost
```

The demo input lives in [examples/byo-minimal](examples/byo-minimal). Its guide
shows how to replace the toy rows with your own paired task outcomes.

## Demo reports

Committed reports are the worked evidence: each is tied to a declared study,
fixture, and reproducible analysis path.

## Example reports

| Report | Shows |
| --- | --- |
| [GAIA HAL Generalist](reports/gaia-hal-generalist/report.md) | `hedge_on_cost` under one HAL harness. |
| [TAU-bench Airline Tool Calling](reports/tau-bench-airline-tool-calling/report.md) | Multiple claims, including `hedge_on_cost` and `drop_from_shortlist`, with `as_reported_only` cost provenance. |
| [HumanEval Direct Completion](reports/humaneval-direct-completion/report.md) | Controlled original-evidence audit. |
| [SWE-bench Verified OpenHands](reports/swe-bench-verified-openhands/report.md) | `switch` with `cost_not_available` suppression. |
| [Terminal-Bench 2.0 Mux](reports/terminal-bench-2-mux/report.md) | Public Mux submissions with `cost_not_available` suppression. |
| [BYO minimal](reports/byo-minimal/report.md) | Small synthetic BYO example with a `switch` verdict. |

## Decision pattern gallery

The decision gallery is synthetic, not benchmark evidence. It exists so readers
can see the remaining verdict patterns — `hold`, `rerun_more_n`, and
`inconclusive_no_action` — render in a full report.

- [reports/decision-gallery/report.md](reports/decision-gallery/report.md)
- [examples/decision-gallery/README.md](examples/decision-gallery/README.md)

## Bring your own data

The one-command flow:

```bash
eval-audit audit my-study/study.yaml --runs my-study/runs.parquet
```

It writes deterministic artifacts under `reports/<study_id>/`: `check.json`,
`analysis.json`, `report.md`, and `summary.json`. Each report carries a
copyable summary generated from those artifacts. For the committed
`byo-minimal` example it reads:

> Claim `alice_vs_bob` verdict `switch` for `alice` vs `bob`: delta +40.00 pp
> with bootstrap CI [+10.00 pp, +70.00 pp]; evidence readiness
> `ready_with_warnings`. Cost caveat: treatment cost is 2.00x control.

Add `--html` for a static view alongside the Markdown.

To gate a CI pipeline on the evidence:

```bash
eval-audit gate my-study/study.yaml --runs my-study/runs.parquet \
  --min-readiness ready_with_warnings \
  --allow-verdict switch \
  --allow-verdict hold
```

Review multiple completed audits as an evidence index. The portfolio reads
existing `summary.json` artifacts — it does not recompute analyses, and its rows
are declared audits rather than a universal model ordering:

```bash
eval-audit portfolio reports --out portfolio.md   # or --json
```

### Step-by-step flow

`audit` bundles the pipeline. The individual steps are also exposed for
inspection and reproducibility:

```bash
eval-audit init my-study
# edit my-study/make_runs.py and my-study/study.yaml
python my-study/make_runs.py
eval-audit validate my-study/runs.parquet my-study/study.yaml
eval-audit check my-study/study.yaml --runs my-study/runs.parquet
eval-audit analyze my-study/study.yaml --runs my-study/runs.parquet
eval-audit report my-study/study.yaml --runs my-study/runs.parquet --skip-validation
```

`validate` checks the input schemas in isolation. `check` evaluates whether the
declared comparison is audit-ready. `report --skip-validation` bypasses the
source-checkout synthetic-validation gate and warns; it is meant for inspecting
the renderer, not for publishing evidence. `report.md` is the canonical
reproducibility artifact either way.

References:

- [examples/byo-minimal/README.md](examples/byo-minimal/README.md) — worked example
- [docs/INPUT_CONTRACT.md](docs/INPUT_CONTRACT.md) — `runs.parquet` field reference
- [docs/STUDY_SCHEMA.md](docs/STUDY_SCHEMA.md) — `study.yaml` field reference

## Work from source

```bash
uv sync --extra dev
make check
```

Useful targeted commands:

```bash
uv run eval-audit spec validate studies/gaia-hal-generalist.yaml
uv run eval-audit audit examples/byo-minimal/study.yaml \
  --runs examples/byo-minimal/runs.parquet \
  --out-dir /tmp/eval-audit-reports
uv run eval-audit analyze studies/gaia-hal-generalist.yaml --out-dir /tmp/eval-audit-reports
uv run eval-audit report studies/gaia-hal-generalist.yaml --out-dir /tmp/eval-audit-reports
uv run eval-audit portfolio reports --out /tmp/eval-audit-portfolio.md
```

Snapshot updates are explicit:

```bash
UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py
```
