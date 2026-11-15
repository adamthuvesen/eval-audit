# Agentic development reassessment

Date: 2026-11-05. Baseline: `c482c619bb48556042aa85d1c10d87f5f6f7a995`.
Scope: local Python methodology toolkit, installed CLI, committed evidence, and offline development workflow.

## Assessment

The baseline was not excellent despite its passing suite of 353 tests.
Validation differed between commands, report settings could contradict analysis, and publication could leave misleading partial output.
Source lookup also attached benchmark metadata to unrelated BYO input.

The implementation now has one owner for evidence preparation, inference settings, source binding, and artifact publication.
Independent reviews found additional failure cases. Those cases were fixed and reviewed again.
The final rating is **4/5: excellent local agentic development experience**, with the final gate recorded below.

This is an ordinal engineering judgment, not a measured performance score.
The rubric is: 1 instructions only, 2 partial enforcement, 3 integrated enforcement,
4 independent adversarial verification, 5 additional cross-platform and live operational evidence.
Excellence requires every axis to reach 4 with no unresolved material local defect.

| Axis | Baseline weakness | Final rating and evidence |
| --- | --- | --- |
| Ownership | Duplicated readiness and analysis checks | 4: one prepared-evidence boundary, one audit builder, one publisher |
| Valid states | Coercion, duplicate observations, inconsistent run totals, permissive summaries | 4: strict input models, relational comparability, typed artifact contracts |
| Verification | Source tests could pass while an installed report required pytest | 4: full local gate, external wheel workflow, fault injection, finite calibration |
| Discoverability | Inaccurate instructions and opaque repair paths | 4: ownership map, generated schemas, focused commands, structured diagnostics |
| Evidence integrity | Implicit provenance, stale settings, partial completion | 4: actual source binding, result-owned settings, completion markers and hashes |

The architecture advisor independently recommended stopping after final verification.
Additional frameworks or an execution backend would expand the toolkit's scope without addressing a demonstrated remaining requirement.

## Implemented changes

1. `evidence.py` validates canonical rows, takes an owned study copy, scopes declared agents, and checks comparability.
   Readiness, analysis, audit, report, and gate share these guarantees.
   Unclaimed Pareto competitors must have valid task sets and replication too.
2. Canonical booleans and numeric values no longer rely on coercion.
   HAL adapters decode their source representations explicitly before canonical validation.
   Duplicate observation keys and inconsistent reported totals fail with diagnostics.
3. `AnalysisSettings` owns alpha, seed, and iteration count.
   Paired inference shares sorted task means. Reports reject mismatched settings and study identities.
4. Sensitivity recomputes whole-study correction families, intervals, and Pareto membership.
   Unavailable comparisons have no verdict. Quality exclusion preserves baseline cost accounting.
   MDE wording describes precision, without claiming power or an immutable future verdict.
5. `build_audit` completes computation before writes. `publish_artifacts` owns publication and writer locking.
   Faults roll back ordinary writes. Interrupted writes remain visibly incomplete.
   Portfolio readers reject invalid or stale summaries and ignore unpublished staging directories.
6. Summary schema version 1 retains filenames and fields while tightening values, consistency, and path containment.
   `analysis.json` adds settings and retains the legacy top-level bootstrap seed.
7. Provenance follows the selected file. Known residual-risk documents require exact fixture and study bindings.
   HumanEval retains its five documented risks. Copied or unrelated BYO files inherit no receipts or documents.
8. The installed CLI works without development dependencies. Relative `init --cwd` works outside the checkout.
   `report` and `audit` publish complete artifacts. `--skip-validation` remains a deprecated no-op.
9. Shared fixture I/O has normal type and test coverage.
   Replay uses immutable source caches. Refresh uses explicit pinned revisions and bounded requests.
10. HumanEval host grading refuses untrusted execution without an isolated backend.
    The private trusted-fixture helper requires a completed-check receipt and distinguishes infrastructure failures.
11. Gallery calibration uses the authoritative decision context instead of recomputing Pareto membership.
    Stale success-count and p-value descriptions were corrected. The generated parquet hash stayed unchanged.
12. Locked setup, focused Make targets, generated JSON Schema, and ownership documentation guide future changes.
    Existing dependencies remain sufficient. No dependency was added or upgraded.

See [architecture](../architecture.md) for the enforcement hierarchy and why each remaining check needs more than types.
See [testing](../testing.md) for exact commands and prerequisites.

## Compatibility and intentional changes

The v0 methodology remains success-rate, higher-is-better, task-paired, frequentist, and within one harness.
Canonical observation keys, baseline accounting, report filenames, and summary version 1 remain unchanged.
No committed source parquet or historical grade was changed.

Previously accepted malformed inputs now fail. Fix canonical values rather than depending on coercion.
Study IDs cannot escape an output root or use the reserved `.audit-stage-` prefix.
Invalid or inconsistent historical summaries must be regenerated through `audit` or `report`.

Sensitivity tables intentionally change when alpha changes an interval or another claim changes the family.
The HumanEval and decision-gallery alpha=0.01 scenarios now report the resulting cost-based verdict.
These are sensitivity corrections. Baseline numerical conclusions remain unchanged.

Fixture refresh now requires explicit revision selection and review before replacing differing evidence.
Historical source caches are unavailable. New replay support does not reconstruct missing historical bytes.
Historical HumanEval outputs retain their original meaning and have not been retrospectively regraded.

## Verification evidence

Final complete gate: `make check` passed on implementation commit `6138a03`, after gallery consolidation and demo regeneration.
It checked the lockfile, Ruff lint, formatting, mypy across 59 source files, and 490 tests.
No tests were skipped in the complete run.
Two SciPy precision-loss warnings occurred on nearly constant synthetic differences.
They remain visible. The associated behavior and finite calibration tests passed.

- Local environment: macOS, Python 3.11.17, locked dependencies.
- The baseline comparison used six committed datasets totaling 2,550 rows.
  With 1,000 bootstrap draws and seed 42, estimates, intervals, counts, costs, and Pareto results matched.
  Four complete analysis payloads matched exactly after removing additive settings metadata.
  Gallery and Terminal-Bench p-values differed only by floating-point rounding below `1e-17` in the observed comparisons.
  Sorting removes the old task-order dependence. These comparisons do not validate upstream evidence quality.
- Six report snapshot diffs were inspected before regeneration, then all seven snapshot tests passed normally.
- The wheel test installs exact locked runtime artifacts into an external environment without pytest.
  It exercises version, relative init, validation, audit, report, gate, and portfolio.
- Artifact failure cases cover staging, replacement, cleanup, interruption, symlinks, competing writers, and unrelated-file preservation.
- Evidence failures cover malformed values, missing competitors, task mismatch, replication mismatch, duplicates, and inconsistent totals.
- Source tests cover actual registered paths, relative paths, copied bytes, wrong identities, and missing sources.
- Seven synthetic tests include recovery and finite calibration across 128 independent fixed-seed draws.
  The calibration bounds were declared before execution. They cover specific null and large-effect scenarios only.
- Offline fixture tests exercise replay, corrupt hashes, invalid normalized data, and promotion rollback.
  Their constructed caches are not the missing historical raw source caches.

## History and review

| Evidence | What was verified |
| --- | --- |
| `28c3f26`, duplicate and replicate validation fix | The mistake class is enforced across public analysis and readiness, including unclaimed competitors |
| `5c39306`, sorted task IDs for deterministic bootstrap | Both paired inference paths now share sorted task means and row-order tests |
| `c41e209`, multi-claim report fix | Multi-claim report and snapshot coverage remains active |
| `716323a`, grader-crash classification fix | Historical failure handling remains explicit, with host execution refused |
| `23985db`, synthetic fixture seed adjustment | New finite calibration uses independent draws instead of a single selected recovery fixture |
| `5dc43c6`, source-distribution hygiene | Packaging tests retain source-distribution exclusions and add external installed-wheel verification |

A controlled early-exit fixture was run against grader code from `716323a`.
That revision returned success after `sys.exit(0)`. The current trusted-fixture helper returned `incomplete_execution`.
This is a replay of a newly demonstrated defect in historical code, not a claim that a past incident was recorded.
Other history rows are failure-class checks, not complete historical-commit executions.

Independent methodology review found a cost-suppression sensitivity defect during implementation.
The fix preserves suppression when costs are unavailable and blocks missing competitors only when Pareto is computed.
The reviewer independently verified the fix with 84 targeted tests and reported no remaining findings.

Independent application review found unpublished staging discovery and missed first-publication interruption.
A second pass found a study-ID collision with the staging prefix.
All three were fixed. The reviewer reproduced the final rejection and reported no remaining findings.
The broader application re-review passed 109 focused tests before the final namespace fix.
The reviewer also approved the final gallery consolidation without additional findings.

## Limits and stopping criteria

Hosted CI, Linux, Windows, network filesystem locking, and live upstream refresh were not executed in this task.
No provider calls, deployment, or container execution was performed.
The repository still does not provide an untrusted benchmark execution backend.
Local success does not prove those environments or universal statistical calibration.

Seven real CLI audit/report runs regenerated the committed examples with 10,000 draws and seed 42.
Their portfolio contains 11 complete claims. Artifact hashes validate, including the BYO HTML report.
Report footers identify implementation commit `6138a03`. Source parquet files remain unchanged.

Stop when the full local gate passes, the committed examples are inspectable and internally consistent,
and independent reviewers have no remaining material findings in the implemented scope.
Those criteria assess ownership, useful feedback, and correct behavior. Test count alone is not the criterion.

All stopping criteria were met. No unresolved review findings remain in the implemented scope. All work stayed local.
