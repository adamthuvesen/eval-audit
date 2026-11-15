# Ingest design rules

Adapters in [eval_audit/ingest](../eval_audit/ingest) normalize public benchmark
artifacts into canonical task-level `RunRecord` rows.

- Preserve source semantics rather than smoothing over inconvenient data.
- Do not silently swap data sources during scouting. Record gate failures and
  provenance honestly under [scouting/](../scouting).

## Cost provenance modes

Cost provenance is first-class. Each adapter declares exactly one mode:

- **`reconciled`**: reconstructed per-task cost matches reported totals within ~1%.
- **`as_reported_only`**: reconstruction does not reconcile; this state MUST
  stay visible in reports rather than being smoothed away.
- **`partial`**: incomplete provenance, accepted when the selected cost basis is complete.
- **`cost_not_available`**: the explicit "no honest cost data" mode for public
  artifacts that expose neither tokens nor reported totals (e.g. SWE-bench
  Verified OpenHands submissions). Both cost fields MUST be null on every row;
  the report suppresses Pareto and per-success cost columns; `analyze()` sets
  `pareto_status="suppressed_cost_not_available"`; `decision_impact` cannot
  return `hedge_on_cost`.

Never fabricate cost (zeros, stale price tables) to dodge `cost_not_available`.

## Shared evidence boundary

`prepare_evidence()` in `eval_audit/evidence.py` validates canonical rows and establishes the declared agent scope.
Public analysis and readiness checks use the same structured diagnostics.
`check_prepared_evidence()` reuses those diagnostics after preparation.

Every declared agent must have rows under the study harness.
Every declared agent must share task coverage and the declared replication count.
Duplicate observation keys fail validation before paired analysis.
Reported totals must have one unique non-null value per agent and run when they supply the cost basis.
Partial cost provenance remains accepted when its chosen cost basis is complete.
Unrelated agents are excluded once, with their IDs and row count recorded in a scope diagnostic.

HAL adapters convert integer 0/1 success flags, timestamp strings, and JSON partial-credit values before canonical validation.
Generic parquet loading requires canonical physical types. It never discards a coercion that analysis would need.
