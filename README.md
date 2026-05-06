# eval-audit

`eval-audit` turns completed benchmark runs into deterministic reports
that tell you whether the result is solid enough to confidently say that one model is superior to another.

Give it the comparison you want to evaluate, paired per-task outcomes,
inference settings, and cost data. It answers one question:

> Is the claim that Model B beats Model A large, reliable, and cost-aware
> enough to act on?

It audits evidence from runs that already exist. It does not run benchmarks
or explain trace-level failures.

## Install

```bash
uv tool install eval-audit
```

Or:

```bash
pipx install eval-audit
```

Check the install:

```bash
eval-audit --version
```

## What You Get

The main artifact is a deterministic Markdown report with:

- verdict and claim status
- paired uncertainty around the treatment-control effect
- target-MDE / resolution context
- cost and cost-provenance caveats
- robustness review
- residual risks
- reproducibility footer with evidence-readiness metadata

Each claim receives one decision verb:

| Verdict | Meaning |
| --- | --- |
| `switch` | Treatment is better enough to choose. |
| `hold` | Control remains the better choice. |
| `drop_from_shortlist` | Treatment is dominated on cost-quality. |
| `rerun_more_n` | Evidence is under-resolved; collect more paired tasks. |
| `hedge_on_cost` | Quality is unclear, so cost should drive the choice. |
| `inconclusive_no_action` | The audit does not support a change. |

## Demo reports

Committed reports show the supported evidence shapes. They are not leaderboard
rows; each is tied to a declared study, fixture, and reproducible analysis path.

## Example reports

| Report | Shows |
| --- | --- |
| [GAIA HAL Generalist](reports/gaia-hal-generalist/report.md) | `hedge_on_cost` under one HAL harness. |
| [TAU-bench Airline Tool Calling](reports/tau-bench-airline-tool-calling/report.md) | Multiple claims, including `hedge_on_cost` and `drop_from_shortlist`, with `as_reported_only` cost provenance. |
| [HumanEval Direct Completion](reports/humaneval-direct-completion/report.md) | Controlled original-evidence audit. |
| [SWE-bench Verified OpenHands](reports/swe-bench-verified-openhands/report.md) | `switch` with `cost_not_available` suppression. |
| [Terminal-Bench 2.0 Mux](reports/terminal-bench-2-mux/report.md) | Public Mux submissions with `cost_not_available` suppression. |
| [BYO minimal](reports/byo-minimal/report.md) | Small synthetic BYO example with a `switch` verdict. |

Cross-harness comparisons are warnings, not audits:
[reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md).

## Decision pattern gallery

The decision gallery is synthetic, not benchmark evidence. It exists so readers
can see verdict patterns render in a full report: `hold`, `rerun_more_n`, and
`inconclusive_no_action`.

- [reports/decision-gallery/report.md](reports/decision-gallery/report.md)
- [examples/decision-gallery/README.md](examples/decision-gallery/README.md)

## Bring your own data

The canonical flow is:

```bash
eval-audit init my-study
# edit my-study/make_runs.py and my-study/study.yaml
eval-audit validate my-study/runs.parquet my-study/study.yaml
eval-audit check my-study/study.yaml --runs my-study/runs.parquet
eval-audit analyze my-study/study.yaml --runs my-study/runs.parquet
eval-audit report my-study/study.yaml --runs my-study/runs.parquet --skip-validation
```

`validate` checks the input schemas in isolation. `check` evaluates whether the
declared comparison is audit-ready.

References:

- [examples/byo-minimal/README.md](examples/byo-minimal/README.md)
- [agents/docs/INPUT_CONTRACT.md](agents/docs/INPUT_CONTRACT.md) for `runs.parquet`
- [agents/docs/STUDY_SCHEMA.md](agents/docs/STUDY_SCHEMA.md) for `study.yaml`

## Quickstart

Create and run a tiny bring-your-own-data audit:

```bash
eval-audit init my-first-audit
cd my-first-audit
eval-audit validate runs.parquet study.yaml
eval-audit check study.yaml --runs runs.parquet
eval-audit analyze study.yaml --runs runs.parquet
eval-audit report study.yaml --runs runs.parquet --skip-validation
```

The report is written to:

```text
reports/my-first-audit/report.md
```

`--skip-validation` is for installed-package demos. For publishable evidence
from a source checkout, run `make check`.

## Inputs

`eval-audit` needs two files:

- `study.yaml`: benchmark/task family, harness, agents, outcome, claims,
  inference settings, and cost view.
- `runs.parquet`: one row per agent-task observation, including `agent_id`,
  `harness`, `task_id`, `success`, `outcome_status`, token/cost fields, and
  `cost_provenance`.

Current scope is intentionally narrow: `success_rate`, `higher_is_better`,
paired task-level comparisons, one harness, frequentist intervals/corrections,
cost provenance, and Markdown reports.

## Work from source

```bash
uv sync --extra dev
make check
```

Useful commands:

```bash
uv run eval-audit spec validate studies/gaia-hal-generalist.yaml
uv run eval-audit analyze studies/gaia-hal-generalist.yaml
uv run eval-audit report studies/gaia-hal-generalist.yaml
```

Snapshot updates are explicit:

```bash
UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py
```
