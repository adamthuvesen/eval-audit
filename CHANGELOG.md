# Changelog

All notable changes to `eval-audit` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The repo's pre-1.0 milestones (v1.0 through v1.5) shipped during the same week as
the inaugural 1.0.0 release; their dated entries below are mapped to synthetic
SemVer tags so a reader can navigate the methodology history.

## [Unreleased]

## [1.0.0] — 2026-05-03

Inaugural PyPI-shaped release. Methodology and schema are stable; the contract
that started with `schema_version: 1` and the four evidence modes (public-data
reanalysis, BYO, synthetic decision-pattern gallery, controlled original-evidence
exhibit) is now backed by a packaged distribution surface.

### Added

- `pyproject.toml` polished with index-ready metadata: `description`, `keywords`,
  `classifiers`, `authors`, `license`, and `[project.urls]` (Homepage, Repository,
  Issues, Changelog).
- `CHANGELOG.md` (this file) walking the project's milestone history with
  references to the fixtures and snapshots each milestone landed.
- `.github/workflows/ci.yml` runs `make check` on push and pull request against
  any branch (broadened from main-only); CI badge surfaced in `README.md`.
- `README.md` "Install" section documenting `uv tool install eval-audit` and
  `pipx install eval-audit` alongside the existing source-checkout `Quickstart`.
- `README.md` "First audit in five minutes" walk-through using the install-path
  CLI against the BYO toy fixture.
- `tests/cli/test_version_install_path.py` regression test asserting
  `eval-audit --version` resolves through `importlib.metadata` (works under both
  source checkout and `uv tool install`).

### Changed

- `eval_audit/__init__.py` `__version__` now reads from package metadata via
  `importlib.metadata.version("eval-audit")` — single source of truth in
  `pyproject.toml`, no hardcoded duplicate.
- Package version bumped from `0.1.0` → `1.0.0`.

## [0.5.0] — 2026-05-03 — Controlled real-evidence Exhibit C

Added the fourth evidence mode: a small, predeclared, paired audit on real model
runs authored end-to-end, distinct from public-data reanalysis (Exhibits A/B),
BYO, and the synthetic gallery. Source: `add-controlled-real-evidence-exhibit`.

### Added

- `studies/exhibit-c.yaml` — predeclared StudySpec with `analysis_mode: preregistered`,
  30-task HumanEval slice (seed=42), Claude Haiku 4.5 vs Claude Sonnet 4.6 under
  the `eval-audit/exhibit-c-direct-v1` thin direct-completion harness, two reruns
  per (agent, task) at temperature=0.
- `examples/exhibit-c/runs.parquet` — canonical RunRecord fixture (120 rows; the
  path of record because provider non-determinism prevents byte-identical
  regeneration from API).
- `reports/exhibit-c/{analysis.json,report.md}` — rendered audit producing
  verdict `inconclusive_no_action` (delta +11.67 pp, CI [+1.67, +23.33], adjusted
  p = 0.0504 just above α=0.05).
- `tests/report_snapshots/exhibit-c-report.md` — committed snapshot.
- `scouting/exhibit-c-decision.md` and `scouting/exhibit-c/run-plan.md` —
  pre-outcome design artifact and run plan, with two pre-decision corrigenda
  recorded honestly (Sonnet model_id typo caught on HTTP 404; grader indentation
  normalization).
- `scouting/exhibit-c/{run.py,grade.py,normalize.py,price-table.yaml,humaneval-tasks-30.jsonl,NOTICE,README.md}` — harness scripts and reproducibility recipe.
- New capability: `controlled-evidence-exhibits`.
- `eval_audit/report/markdown.py` — controlled-evidence Provenance block (run_plan
  link, decision_doc link, task source, harness + commit hash, model arms, rerun
  policy, run dates, price-table date, per-row cost-provenance class) when
  `analysis_mode == "preregistered"`.

### Fixed

- `eval_audit/report/sensitivity.py` — `errored_policy=excluded` perturbation now
  short-circuits when `n_errored == 0` for the claim's arms (no-op should be
  no-op) and uses the same paired-p / correction-adjusted rejection basis as the
  baseline, rather than substituting bootstrap CI overlap. Previously could
  produce spurious verdict flips near the boundary (e.g. p = 0.0504 with a
  one-sided CI). Affected the decision-gallery snapshot, which was regenerated.
- `inconclusive_no_action` verdict rationale rewritten to accurately describe
  the only state that produces it (one-sided CI but correction-adjusted p does
  not reject at α).

## [0.4.1] — 2026-05-03 — Synthetic decision-pattern gallery

Source: `add-decision-pattern-gallery`.

### Added

- `studies/decision-gallery.yaml` and `examples/decision-gallery/runs.parquet` —
  deterministic synthetic data covering verdicts the public-data exhibits do not
  naturally produce (`hold`, `rerun_more_n`, `inconclusive_no_action`).
- `reports/decision-gallery/report.md` — rendered gallery audit.
- `tests/report_snapshots/decision-gallery-report.md` — committed snapshot.
- `examples/decision-gallery/README.md` — worked walkthrough explaining each
  claim's calibration and which decision rule it triggers.
- `README.md` "Decision pattern gallery" section labelling the gallery as
  synthetic methodology demonstration, not benchmark evidence.
- New capability: `decision-pattern-gallery`.

## [0.4.0] — 2026-05-03 — Decision explainer + example reports

Source: `add-decision-explainer-and-gallery`.

### Added

- Verdict-rationale block in the audit summary translating each decision verb
  into recommended action (rule that fired, what it means, action implied),
  surfaced via `eval_audit/report/markdown.py`.
- README "Example reports" section indexing the real-data committed reports by
  decision verb (hedge_on_cost, hedge_on_cost / drop_from_shortlist, switch).

## [0.3.0] — 2026-05-03 — schema_version + public StudySpec docs

Source: `add-schema-versioning`.

### Added

- `schema_version: 1` field on every `StudySpec`, validated by `eval_audit/schema/study.py`.
- Public schema reference: `agents/docs/INPUT_CONTRACT.md` (canonical RunRecord
  field-by-field reference) and `agents/docs/STUDY_SCHEMA.md` (StudySpec
  field-by-field reference).
- Schema contract tests protecting public field names and error wording.

## [0.2.0] — 2026-05-03 — BYO parquet loader + init/validate

Source: `add-byo-runs-loader` and `add-byo-init-validate`.

### Added

- `eval_audit/ingest/generic.py::load_run_records` — generic BYO parquet loader
  validating against the canonical RunRecord schema.
- `eval-audit analyze --runs PATH` and `eval-audit report --runs PATH` flags
  bypass the benchmark-keyed adapter and load a canonical parquet directly.
- `eval-audit init <name>` — scaffold a new BYO study directory
  (`study.yaml`, `make_runs.py`, `runs.parquet`, `README.md`) with round-trip
  validation out of the box.
- `eval-audit validate <runs> <study>` — standalone pre-flight check.
- `eval-audit --version` (top-level flag, sourced via `importlib.metadata`).
- `examples/byo-minimal/` — toy 2-agent 10-task worked example.

## [0.1.0] — 2026-05-02 — Initial verdict-grade audit reports

Source: `add-audit-summary-header`, `add-resolution-planning`,
`add-robustness-review`, `refresh-readme-for-v1`, plus the foundational
`v0-exhibit-a-reanalysis` work.

### Added

- Audit-summary header rendered first in every report (Verdict, Claim status,
  Why, What would change it, Reviewer pushback).
- Resolution planning: target_mde + bootstrap CI half-width → required-N
  estimate (variance-fixed scaling).
- Robustness review: per-claim survives/does-not-survive table across
  multiple-comparison correction, errored-row policy, cost-threshold
  sensitivity, target MDE, and cost provenance.
- Verdict-sensitivity sub-block per claim, perturbing alpha, errored-row policy,
  correction method, and cost-gap threshold.
- `reports/exhibit-a/report.md` — GAIA HAL Generalist reanalysis (Claude 3.7
  Sonnet vs o4-mini High) producing verdict `hedge_on_cost`.
- `reports/exhibit-b/report.md` — TAU-bench Tool Calling three-arm reanalysis
  exercising `as_reported_only` cost-provenance path; verdicts `hedge_on_cost`
  and `drop_from_shortlist`.
- `tests/report_snapshots/exhibit-a-report.md` and `exhibit-b-report.md` —
  committed snapshots.
- README "What you'll see" section quoting the rendered Audit Summary and
  Robustness Review verbatim.

[Unreleased]: https://github.com/adamthuvesen/eval-audit/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/adamthuvesen/eval-audit/releases/tag/v1.0.0
