# AGENTS.md

Instructions for AI coding agents working in this repository. This file is the
canonical local guide for Codex, Claude, Cursor, Cortex, and any other agent.
The closest `AGENTS.md` or `CLAUDE.md` wins.

## What This Repo Is

`eval-audit` is a small Python methodology toolkit for turning agent benchmark
claims into auditable model-selection decisions.

It is not a benchmark runner, leaderboard, tracing system, composite-score
factory, or causal model of scaffolds. Its current value is narrower and
sharper: declared study specs, validated task-level records, paired analysis,
cost-aware reports, and deterministic evidence artifacts.

Keep that shape intact.

## Non-Negotiables

- Preserve the v0 contract unless the user explicitly asks to expand it:
  `success_rate`, `higher_is_better`, task-level paired comparisons within one
  harness, frequentist intervals/corrections, markdown reports.
- Do not make cross-harness comparisons look causal. If harnesses differ, say
  so plainly and preserve the existing refusal behavior.
- Do not hide uncertainty. Confidence intervals, adjusted p-values, target MDE,
  errored-row policy, cost provenance, and sensitivity tables are part of the
  product, not decorations.
- Do not silently broaden unsupported outcomes such as latency, cost,
  lower-is-better metrics, partial credit, or composite scores. Add them only
  with metric-specific schema, inference, report semantics, and tests.
- Reports must be deterministic and reproducible. Snapshot changes are
  intentional artifacts, not incidental churn.
- Fixtures and scouting outputs are evidence. Treat provenance, sampling seeds,
  cost reconciliation, and source notes as first-class.
- Keep changes small, explicit, and methodology-aware. No drive-by refactors.

## Work Method

For non-trivial work, use the project sequence:

1. Read repo docs: `README.md`, relevant files under `scouting/`, `reports/`,
   and any study/spec files involved.
2. Recall prior context when available.
3. Inspect the actual code and tests.
4. Use external docs only for external APIs, dependencies, or current facts.

For small local edits, stay lightweight, but do not speculate. Confirm against
the nearest source of truth.

Before claiming a change is done:

- Read the full file(s) you changed.
- Run the relevant tests or explain exactly why you did not.
- If you renamed or moved anything, grep the whole repo for old names.
- Check `git diff --check` for whitespace and conflict marker mistakes.
- Check `git status --short` and mention generated or unrelated changes.

## Repo Map

```text
eval_audit/
  schema/      StudySpec and RunRecord validation
  ingest/      public-data fixture adapters
  stats/       intervals, bootstrap, correction, analysis, Pareto frontier
  report/      markdown rendering, decision rules, sensitivity tables
  spec/        deterministic study-spec rendering
  cli.py       Typer CLI

studies/       declared study YAML files
reports/       committed demo reports and analysis JSON
scouting/      fixture provenance, candidate inventories, decisions
tests/         schema, ingest, stats, report, CLI, snapshot, validation tests
```

## Commands

Use `uv`. Do not introduce a second dependency workflow.

```bash
uv sync --extra dev
make test
make lint
make check
```

Useful targeted commands:

```bash
uv run eval-audit spec validate studies/exhibit-a.yaml
uv run eval-audit spec render studies/exhibit-a.yaml --out /tmp/exhibit-a-spec.md
uv run eval-audit analyze studies/exhibit-a.yaml
uv run eval-audit report studies/exhibit-a.yaml
uv run pytest tests/report/test_snapshot.py
uv run pytest -m synthetic_validation tests/synthetic_validation
```

Snapshot updates are explicit:

```bash
UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py
```

Only update snapshots when the rendered report change is intentional and you
have reviewed the diff.

## Design Rules

### Schema

- Prefer strict Pydantic models with `extra="forbid"`.
- Validate declarations at the boundary. Bad study specs should fail loudly
  before analysis.
- Keep schema declarations aligned with engine behavior. Never accept a field
  that the engine ignores in a decision-relevant way.
- When expanding v0 scope, update schema, analysis, report rendering,
  snapshots, CLI behavior, and docs together.

### Ingest

- Adapters should normalize public benchmark artifacts into canonical
  task-level records.
- Preserve source semantics rather than smoothing over inconvenient data.
- Cost provenance matters:
  - `reconciled` means reconstructed per-task cost matches reported totals.
  - `as_reported_only` must remain visible in reports when reconstruction does
    not reconcile.
- Do not silently swap data sources during scouting. Record gate failures and
  provenance honestly.

### Stats

- Task is the unit of paired analysis. Avoid naive row-level shortcuts that
  ignore task clustering.
- Errored rows count as failures in headline denominators while still surfacing
  `n_errored`.
- Keep bootstrap seeds and iteration counts explicit where reproducibility
  matters.
- Multiple-comparison correction is part of the declared claim family. Do not
  report unadjusted significance as the decision.
- Prefer clear, boring statistical code over clever abstractions.

### Reports

- Markdown reports are decision artifacts. They should answer what a model
  selector should do, not just list numbers.
- Keep report output deterministic: stable ordering, stable formatting, stable
  clocks in tests, and reviewed snapshots.
- Surface caveats near the claims they affect. Do not bury cost or provenance
  caveats in generic footnotes.
- The allowed decision vocabulary is intentional: `switch`, `hold`,
  `drop_from_shortlist`, `rerun_more_n`, `hedge_on_cost`, and
  `inconclusive_no_action`.

### CLI

- The Typer CLI should stay minimal and reproducible.
- CLI failures should be clear, non-zero, and tied to the invalid input or
  failed validation gate.
- Do not add network-dependent CLI paths without an explicit user request and
  a reproducibility story.

## Testing Expectations

Match test scope to risk:

- Schema changes: schema tests, invalid-case tests, and CLI validation tests.
- Ingest changes: adapter tests plus provenance/cost-path tests.
- Statistical changes: unit tests, property tests where useful, and synthetic
  recovery validation when behavior could affect conclusions.
- Report changes: renderer tests, decision-impact tests, sensitivity tests, and
  snapshot review.
- CLI changes: command tests and at least one realistic study path.

For report-affecting work, run the snapshot test. For methodology-affecting
work, run `make check` plus the synthetic-validation gate when relevant.

## Style

- Python 3.11+, type hints, `pathlib.Path`, Pydantic for validated data.
- Use Polars idioms for tabular work already in the codebase.
- Keep functions named by intent. Avoid abbreviations that obscure the
  statistical meaning.
- Comments should explain why a methodology choice exists, not restate the
  code.
- Match neighboring code before inventing a new pattern.
- No new dependencies without asking first.
- No notebooks for simple scripts. Use `.py`.

## Git Hygiene

- Commit only when the user asks.
- Never commit secrets, credentials, `.env` files, or AI attribution.
- Stage only intended hunks.
- Do not push, create PRs, or merge without explicit approval in chat.
- Do not commit to `main` without explicit permission.

## When Unsure

Stop and name the uncertainty. In this repo, a cautious refusal is often better
than a polished but unsupported benchmark conclusion.

Good questions:

- Is this a declared reanalysis, exploratory analysis, or a new benchmark
  capability?
- Is the comparison within one harness?
- Is the outcome actually supported by the engine?
- Does the report make the decision implication and caveats visible?
- Can the fixture be regenerated from committed provenance?

