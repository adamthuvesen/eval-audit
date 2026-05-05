# eval-audit

`eval-audit` helps teams decide which model to choose from benchmark evidence.

Given a declared claim, paired task-level results, and costs, it asks:

> Is there enough evidence to switch models, keep the current choice, rerun with more data, or conclude that no model-selection change is supported?

It does not run benchmarks. It audits benchmark evidence after the runs exist.

## What it produces

The main output is a deterministic Markdown report.

Each report starts with:

- a verdict
- whether the claim is supported
- the paired uncertainty around the effect
- the cost comparison, when honest cost data exists
- what would need to change for a clearer decision
- caveats a reviewer should care about

Example: [reports/gaia-hal-generalist/report.md](reports/gaia-hal-generalist/report.md)

## Verdicts

Each claim receives one decision verb.

| Verdict                  | Meaning                                                            |
| ------------------------ | ------------------------------------------------------------------ |
| `switch`                 | The treatment is better enough to choose.                          |
| `hold`                   | The control remains the better choice.                             |
| `drop_from_shortlist`    | The treatment is worse enough to remove.                           |
| `rerun_more_n`           | The result is underpowered; collect more paired tasks.             |
| `hedge_on_cost`          | Quality is not clearly different, so cost should drive the choice. |
| `inconclusive_no_action` | The audit does not support a change.                               |

## When to use it

Use `eval-audit` when you have:

- two or more agents
- the same tasks for each agent
- one harness or scaffold
- task-level outcomes
- a declared comparison you want to defend

Do not use it for:

- model-only claims across different harnesses
- leaderboard ranking
- composite scores
- latency or lower-is-better outcomes
- partial-credit outcomes
- benchmark execution

Those may be useful, but they are outside the current contract.

## Install

With `uv`:

```bash
uv tool install eval-audit
```

Or with `pipx`:

```bash
pipx install eval-audit
```

Check the installed version:

```bash
eval-audit --version
```

## Demo reports

The committed reports show the supported evidence shapes.

They are not leaderboard rows. Each report is tied to a declared study, a
fixture, and a reproducible analysis path.

## Example reports

| Report                                                                             | Shows                                                                                                          |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| [GAIA HAL Generalist](reports/gaia-hal-generalist/report.md)                       | `hedge_on_cost` on GAIA under one HAL harness.                                                                 |
| [TAU-bench Airline Tool Calling](reports/tau-bench-airline-tool-calling/report.md) | Multiple claims, including `hedge_on_cost` and `drop_from_shortlist`, with `as_reported_only` cost provenance. |
| [HumanEval Direct Completion](reports/humaneval-direct-completion/report.md)       | Controlled original-evidence audit on HumanEval.                                                               |
| [SWE-bench Verified OpenHands](reports/swe-bench-verified-openhands/report.md)     | `switch` with `cost_not_available` suppression.                                                                |
| [Terminal-Bench 2.0 Mux](reports/terminal-bench-2-mux/report.md)                   | Public Mux submissions on Terminal-Bench 2.0 with `cost_not_available` suppression.                            |
| [BYO minimal](reports/byo-minimal/report.md)                                       | Small synthetic bring-your-own-data example with a `switch` verdict.                                           |

The cross-harness note is separate because it is a warning, not an audit:
[reports/cross-harness-confound/notes.md](reports/cross-harness-confound/notes.md)

## Decision pattern gallery

The decision gallery is synthetic. It is not benchmark evidence.

It exists so readers can see how these verdicts render in a full report:

- `hold`
- `rerun_more_n`
- `inconclusive_no_action`

Files:

- [reports/decision-gallery/report.md](reports/decision-gallery/report.md)
- [examples/decision-gallery/README.md](examples/decision-gallery/README.md)

## Bring your own data

The recommended path is:

```bash
eval-audit init my-study
python my-study/make_runs.py
eval-audit validate my-study/runs.parquet my-study/study.yaml
eval-audit analyze my-study/study.yaml --runs my-study/runs.parquet
eval-audit report my-study/study.yaml --runs my-study/runs.parquet --skip-validation
```

Then edit:

- `my-study/make_runs.py` so it writes your real task-level records
- `my-study/study.yaml` so the agents and claims match your data

References:

- [examples/byo-minimal/README.md](examples/byo-minimal/README.md) — worked BYO example
- [agents/docs/INPUT_CONTRACT.md](agents/docs/INPUT_CONTRACT.md) — `runs.parquet` field reference
- [agents/docs/STUDY_SCHEMA.md](agents/docs/STUDY_SCHEMA.md) — `study.yaml` field reference

## Quickstart

Scaffold a small bring-your-own-data audit:

```bash
eval-audit init my-first-audit
cd my-first-audit
```

The scaffold includes:

- `study.yaml` — the declared study and claim
- `runs.parquet` — task-level run records
- `make_runs.py` — the script that regenerates `runs.parquet`
- `README.md` — notes for the scaffolded example

Validate the inputs:

```bash
eval-audit validate runs.parquet study.yaml
```

Run the analysis:

```bash
eval-audit analyze study.yaml --runs runs.parquet
```

Render the report:

```bash
eval-audit report study.yaml --runs runs.parquet --skip-validation
```

The report is written to:

```text
reports/my-first-audit/report.md
```

`--skip-validation` is used here because the packaged CLI does not include the
repo's synthetic-validation test suite. For publishable evidence, work from a
source checkout and run the full checks.

## The two inputs

`eval-audit` always needs a study spec and task-level runs.

### `study.yaml`

The study spec declares:

- the benchmark or task family
- the harness
- the agents
- the primary outcome
- the comparison claims
- the inference settings
- the cost view

Reference: [agents/docs/STUDY_SCHEMA.md](agents/docs/STUDY_SCHEMA.md)

### `runs.parquet`

The run data contains one row per agent-task observation.

Important fields include:

- `agent_id`
- `model_id`
- `harness`
- `run_id`
- `task_id`
- `success`
- `outcome_status`
- token counts
- cost fields
- `cost_provenance`

Reference: [agents/docs/INPUT_CONTRACT.md](agents/docs/INPUT_CONTRACT.md)

## Current contract

The supported outcome is:

- `success_rate`
- `higher_is_better`

The supported comparison shape is:

- paired task-level comparisons
- treatment and control run under the same harness
- task identity matched by `task_id`

The supported inference path includes:

- Wilson intervals for per-agent success rates
- paired bootstrap intervals for treatment-control deltas
- paired p-values
- declared multiple-comparison correction
- target-MDE resolution checks

The supported cost path includes:

- Pareto cost-quality view
- cost per success when cost data supports it
- explicit cost provenance
- suppression of cost views when cost is not honestly available

Cross-harness comparisons are rejected. Unsupported outcomes are rejected.
The tool should fail loudly rather than turn unsupported evidence into a
clean-looking report.

## Cost provenance

Cost is part of the audit, not a footnote.

`cost_provenance` tells the report how much to trust the cost data:

| Value                | Meaning                                                             |
| -------------------- | ------------------------------------------------------------------- |
| `reconciled`         | Per-task reconstructed cost matches reported totals closely enough. |
| `as_reported_only`   | Only run-level reported totals are usable.                          |
| `partial`            | Cost is incomplete and reported as a caveat.                        |
| `cost_not_available` | No honest cost data exists; cost columns and Pareto are suppressed. |

The report should show uncertainty in cost provenance as plainly as uncertainty
in quality.

## Work from source

Install development dependencies:

```bash
uv sync --extra dev
```

Validate a study spec:

```bash
uv run eval-audit spec validate studies/gaia-hal-generalist.yaml
```

Render a study spec:

```bash
uv run eval-audit spec render studies/gaia-hal-generalist.yaml --out /tmp/gaia-hal-generalist-spec.md
```

Analyze a committed study:

```bash
uv run eval-audit analyze studies/gaia-hal-generalist.yaml
```

Render a committed report:

```bash
uv run eval-audit report studies/gaia-hal-generalist.yaml
```

Run the local checks:

```bash
make check
```

## Repository map

```text
eval_audit/
  schema/      StudySpec and RunRecord validation
  ingest/      public-data fixture adapters
  stats/       intervals, bootstrap, correction, analysis, Pareto frontier
  report/      markdown rendering, decision rules, sensitivity tables
  spec/        deterministic study-spec rendering
  cli.py       Typer CLI

studies/       declared study YAML files
reports/       committed reports and analysis JSON
scouting/      fixture provenance, candidate inventories, decisions
examples/      BYO and fixture examples
tests/         schema, ingest, stats, report, CLI, snapshot, validation tests
```

## Development commands

```bash
make test
make lint
make check
```

Snapshot updates are explicit:

```bash
UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py
```

Only update snapshots when a rendered report change is intentional and the diff
has been reviewed.

## Project boundary

`eval-audit` is a methodology toolkit for auditable model-selection decisions.

It is not:

- a benchmark runner
- a leaderboard
- a tracing system
- a composite-score factory
- a causal model of scaffolds

That boundary is deliberate. A smaller tool that refuses unsupported claims is
more useful than a broader tool that makes weak evidence look precise.
