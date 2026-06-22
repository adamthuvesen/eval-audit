# AGENTS.md — eval-audit

`eval-audit` is a small Python methodology toolkit for deciding whether
benchmark score differences are large, reliable, and cost-aware enough to
justify switching models. It is not a benchmark runner, leaderboard, tracing
system, composite-score factory, or causal model of scaffolds — keep that shape.

User-level guidance (tone, principles, git etiquette) lives in
`~/.claude/CLAUDE.md` and `~/dotfiles/agents/AGENTS.md` and is *not* duplicated
here. This file is for project-specific facts.

## Layout

```
eval_audit/
├── schema/      StudySpec + RunRecord validation, audit summary shapes
├── ingest/      public-data fixture adapters → canonical task-level rows
├── stats/       intervals, bootstrap, correction, paired analysis, Pareto
├── report/      markdown rendering, decision rules, sensitivity tables
├── spec/        deterministic study-spec rendering
└── cli.py       Typer CLI (entry point eval-audit)

studies/         declared study YAML files
reports/         committed demo reports and analysis JSON
scouting/        fixture provenance, candidate inventories, decisions
examples/        BYO worked example (byo-minimal/)
tests/           schema, ingest, stats, report, CLI, snapshot, doc-parity, synthetic
docs/            field references + per-subsystem design docs — see Index
```

## Quickstart

```bash
uv sync --extra dev
make check        # ruff check + ruff format --check + pytest (the CI gate)
make test         # pytest only
make lint         # ruff check only

uv run eval-audit spec validate studies/gaia-hal-generalist.yaml
uv run eval-audit analyze studies/gaia-hal-generalist.yaml
uv run eval-audit report studies/gaia-hal-generalist.yaml
```

`make check` is the single source of truth for CI — the workflow invokes it
directly. If it passes locally, CI passes.

## Critical Conventions

Non-obvious rules; verify each against code before relying on it.

- **Preserve the v0 contract** unless the user explicitly asks to expand it:
  `success_rate`, `higher_is_better`, task-level paired comparisons within one
  harness, frequentist intervals/corrections, markdown reports. Broadening to
  latency, cost, lower-is-better, partial credit, or composite scores needs
  metric-specific schema, inference, report semantics, and tests — never a
  silent widen.
- **Never make cross-harness comparisons look causal.** If harnesses differ,
  say so plainly and keep the existing refusal behavior.
- **Never hide uncertainty.** Confidence intervals, adjusted p-values, target
  MDE, errored-row policy, cost provenance, and sensitivity tables are the
  product, not decorations.
- **Cost provenance is first-class** and has three explicit modes
  (`reconciled`, `as_reported_only`, `cost_not_available`); never fabricate
  cost to dodge the no-data mode. See [docs/design-ingest.md](docs/design-ingest.md).
- **Reports are deterministic.** Snapshot changes are intentional artifacts, not
  incidental churn; regenerate them only after reviewing the diff. See
  [docs/testing.md](docs/testing.md).
- **`uv` is the only dependency workflow.** No second toolchain, no new deps
  without asking, no notebooks for simple scripts.
- **Keep changes small and methodology-aware.** No drive-by refactors.
- **Never commit secrets, `.env`, or AI-attribution lines.**

## Read The Docs First

Before editing a subsystem, read the matching doc:

| Subsystem | Doc |
| --- | --- |
| Declared study YAML (field reference) | [docs/STUDY_SCHEMA.md](docs/STUDY_SCHEMA.md) |
| BYO run data (`RunRecord` field reference) | [docs/INPUT_CONTRACT.md](docs/INPUT_CONTRACT.md) |
| Schema / validation | [docs/design-schema.md](docs/design-schema.md) |
| Ingest adapters / cost provenance | [docs/design-ingest.md](docs/design-ingest.md) |
| Stats / intervals / Pareto | [docs/design-stats.md](docs/design-stats.md) |
| Reports / decision rules / CLI | [docs/design-reports.md](docs/design-reports.md) |
| Testing scope + snapshot/synthetic gates | [docs/testing.md](docs/testing.md) |

The field references ([STUDY_SCHEMA.md](docs/STUDY_SCHEMA.md),
[INPUT_CONTRACT.md](docs/INPUT_CONTRACT.md)) are pinned to the code by
doc-parity tests in `tests/docs/` — a schema change without a matching doc edit
fails CI. If a doc disagrees with code, fix the doc in the same change.

## Verification

Beyond `make check`, this repo has two gates that bite:

- **Report-affecting work:** run the snapshot test, and only regenerate
  snapshots with `UPDATE_SNAPSHOTS=1` after reviewing the diff.
- **Methodology-affecting work:** run the synthetic-validation recovery gate
  (`uv run pytest -m synthetic_validation tests/synthetic_validation`).

A cautious refusal beats a polished but unsupported benchmark conclusion. When
unsure whether a comparison is within one harness, whether the outcome is
engine-supported, or whether a fixture is regenerable from committed provenance,
stop and name the uncertainty.

## Index

Start with [docs/STUDY_SCHEMA.md](docs/STUDY_SCHEMA.md) and
[docs/INPUT_CONTRACT.md](docs/INPUT_CONTRACT.md) for the data contract, then
follow the per-subsystem design docs above.
