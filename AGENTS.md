# AGENTS.md: eval-audit

`eval-audit` is a small Python methodology toolkit. It decides whether benchmark
score differences are large, reliable, and cost-aware enough to justify a model
switch. It is not a benchmark runner, leaderboard, tracing system,
composite-score factory, or causal model of scaffolds. Keep that shape.

## Commands

```bash
make setup     # locked install, dev extras
make check     # fast lane and first CI job: lock, ruff, import contracts, format, basedpyright, pytest
make fix       # ruff --fix and ruff format
make verify    # drive the real CLI (ARGS=all|list|control|<drive>)
make slow      # slow lane, after check in CI: tests marked `verify` (wheel install, synthetic recovery), then `verify all` + `verify control`

uv run --locked eval-audit spec schema --model study|run|summary
uv run --locked eval-audit report studies/gaia-hal-generalist.yaml --out-dir /tmp/eval-audit-reports
```

Prove changes with `make verify` (`verify-eval-audit` skill at `.agents/skills/verify-eval-audit/`).
Run `make slow` for methodology, CLI, template, or packaging changes.
A stale artifact in `reports/<id>/` fails the fast lane, and the failure prints the regeneration command.
Review the rendered diff before you accept it.
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
| Lower layers never import higher ones; the contract owns the layer order | `pyproject.toml::tool.importlinter`, `Makefile::lint-imports` | 2026-11-06 |
| v0 outcomes are `success_rate`, higher is better | `eval_audit/schema/study.py::_study_invariant_errors`, `tests/stats/test_analyze.py::test_analyze__unsupported_outcome_fails_loudly` | 2026-04-29 |
| Cross-harness claims are refused and write no report | `tests/cli/test_audit_cmd.py::test_audit__cross_harness_refusal_does_not_write_report` | 2026-05-06 |
| Cost provenance has exactly four modes | `eval_audit/schema/enums.py::CostProvenance`, `tests/schema/test_cost_not_available_provenance.py::test_cost_not_available__reports_both_violations_together` | 2026-05-05 |
| Field references match the Pydantic models | `tests/docs/test_study_schema.py::test_study_schema__top_level_fields_match_studyspec`, `tests/docs/test_input_contract.py::test_input_contract__field_list_matches_run_record_schema` | 2026-05-05 |
| Committed reports match a fresh render from committed evidence | `tests/report/test_committed_reports.py::test_committed_reports__match_fresh_render` | 2026-11-06 |
| `uv.lock` matches `pyproject.toml` | `Makefile::lock-check` | 2026-11-05 |
| CI jobs run only setup and one Make target; `slow` waits for `check` | `tests/test_ci_workflow.py::test_ci_workflow__runs_only_make_targets` | 2026-11-06 |
| CI actions pin 40-character SHAs and uv pins an exact version | `tests/test_ci_workflow.py::test_ci_workflow__pins_actions_and_uv_exactly` | 2026-11-07 |
| Local caches and `.env` stay out of the sdist | `tests/packaging/test_sdist.py::test_sdist__excludes_local_caches_and_build_outputs` | 2026-05-22 |
| Estimators recover known effects within declared bounds | `tests/synthetic_validation/test_recovery.py::test_synthetic_validation__per_agent_success_rate_within_tolerance`, `tests/synthetic_validation/test_calibration.py::test_interval_coverage_within_predeclared_binomial_bound` | 2026-04-29 |
| `verify control` must observe FAIL before a verify pass counts | `.agents/skills/verify-eval-audit/verify::control` | 2026-11-06 |
| basedpyright reports zero errors in strict mode, with no baseline file | `pyproject.toml::typeCheckingMode`, `Makefile::typecheck` | 2026-11-07 |
| Paid API calls refuse without approval, before any raw output is written | `scouting/humaneval-direct-completion/run.py::require_approval`, `tests/scouting/test_humaneval_run_spend.py::test_call_api__refuses_without_explicit_approval` | 2026-11-07 |
| Process, network, and paid-SDK modules are banned outside their owner files | `pyproject.toml::tool.ruff.lint.flake8-tidy-imports.banned-api`, `tests/test_module_bans.py::test_module_bans__owners_use_only_their_own_modules` | 2026-11-07 |
| Every citation in this table exists | `tests/docs/test_enforced_rules.py::test_enforced_rules__citations_exist` | 2026-11-06 |
| No file downgrades strict type checking with a `# pyright:` mode comment | `tests/test_strict_mode.py::test_no_file_downgrades_type_checking_mode` | 2026-11-07 |

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
| Test lanes, committed reports, fixture replay | [docs/testing.md](docs/testing.md) |

If a doc disagrees with code, fix the doc in the same change.
