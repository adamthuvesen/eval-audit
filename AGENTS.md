# AGENTS.md: eval-audit

`eval-audit` is a small Python methodology toolkit. It decides whether benchmark
score differences are large, reliable, and cost-aware enough to justify a model
switch. It is not a benchmark runner, leaderboard, tracing system,
composite-score factory, or causal model of scaffolds. Keep that shape.

## Commands

```bash
make setup     # locked install, dev extras
make check     # fast lane and first CI job: lock, ruff, import contracts, format, mypy, pytest
make verify    # slow lane, second CI job: installed-wheel smoke test and synthetic recovery/calibration
UPDATE_SNAPSHOTS=1 uv run --locked pytest tests/report/test_snapshot.py   # only after reviewing the diff

uv run --locked eval-audit spec schema --model study|run|summary
uv run --locked eval-audit audit studies/gaia-hal-generalist.yaml
```

Run `make verify` for methodology, CLI, template, or packaging changes.
For the module owner of each change and focused test commands, read
[docs/architecture.md](docs/architecture.md).

## Judgment Calls

- **Preserve the v0 contract** unless the user explicitly asks to expand it.
  Broadening beyond task-level `success_rate` needs metric-specific schema,
  inference, report semantics, and tests. Never widen silently.
- **Never make cross-harness comparisons look causal.** If harnesses differ,
  say so plainly and keep the refusal.
- **Never hide uncertainty.** Intervals, adjusted p-values, target MDE,
  errored-row policy, cost provenance, and sensitivity tables are the product.
- **Never fabricate cost** to avoid the `cost_not_available` mode.
- A cautious refusal beats a polished but unsupported conclusion. When unsure
  whether a comparison is within one harness, whether the outcome is
  engine-supported, or whether a fixture is regenerable from committed
  provenance, stop and name the uncertainty.
- An import-contract failure means the shared code belongs in a lower layer.
  Move the code down; do not reorder the layers.

## Enforced Rules

| Rule | Enforced by | Added |
| --- | --- | --- |
| Lower layers never import higher ones: schema, ingest, evidence, stats, report, pipeline, cli | `pyproject.toml::[tool.importlinter]`, `Makefile::lint-imports` | 2026-11-06 |
| v0 outcomes are `success_rate`, higher is better | `eval_audit/schema/study.py::must be 'success_rate' in v0`, `tests/stats/test_analyze.py::test_analyze__unsupported_outcome_fails_loudly` | 2026-04-29 |
| Cross-harness claims are refused and write no report | `tests/cli/test_audit_cmd.py::test_audit__cross_harness_refusal_does_not_write_report` | 2026-05-06 |
| Cost provenance has exactly four modes | `eval_audit/schema/enums.py::class CostProvenance`, `tests/schema/test_cost_not_available_provenance.py` | 2026-05-05 |
| Field references match the Pydantic models | `tests/docs/test_study_schema.py`, `tests/docs/test_input_contract.py` | 2026-05-05 |
| Reports are byte-deterministic and match committed snapshots | `tests/report/test_snapshot.py` | 2026-04-29 |
| `uv.lock` is current; `uv` is the only dependency workflow | `Makefile::uv lock --check` | 2026-11-05 |
| CI runs the Make targets, not copies of them | `.github/workflows/ci.yml::run: make check`, `.github/workflows/ci.yml::run: make verify` | 2026-11-06 |
| Local caches and `.env` stay out of the sdist | `tests/packaging/test_sdist.py` | 2026-05-22 |
| Estimators recover known effects within declared bounds | `tests/synthetic_validation/test_recovery.py`, `tests/synthetic_validation/test_calibration.py` | 2026-04-29 |
| Every citation in this table exists | `tests/docs/test_enforced_rules.py` | 2026-11-06 |

## Docs

| Subsystem | Doc |
| --- | --- |
| Ownership and change recipes | [docs/architecture.md](docs/architecture.md) |
| Declared study YAML | [docs/STUDY_SCHEMA.md](docs/STUDY_SCHEMA.md) |
| BYO run data (`RunRecord`) | [docs/INPUT_CONTRACT.md](docs/INPUT_CONTRACT.md) |
| Schema and validation | [docs/design-schema.md](docs/design-schema.md) |
| Ingest adapters and cost provenance | [docs/design-ingest.md](docs/design-ingest.md) |
| Stats, intervals, Pareto | [docs/design-stats.md](docs/design-stats.md) |
| Reports, decision rules, CLI | [docs/design-reports.md](docs/design-reports.md) |
| Test lanes, snapshots, fixture replay | [docs/testing.md](docs/testing.md) |

If a doc disagrees with code, fix the doc in the same change.
