# Ingest design rules

Adapters in [eval_audit/ingest](../eval_audit/ingest) normalize public benchmark
artifacts into canonical task-level `RunRecord` rows.

- Preserve source semantics rather than smoothing over inconvenient data.
- Do not silently swap data sources during scouting. Record gate failures and
  provenance honestly under [scouting/](../scouting).

## Cost provenance modes

Cost provenance is first-class. Each adapter declares exactly one mode:

- **`reconciled`** — reconstructed per-task cost matches reported totals.
- **`as_reported_only`** — reconstruction does not reconcile; this state MUST
  stay visible in reports rather than being smoothed away.
- **`cost_not_available`** — the explicit "no honest cost data" mode for public
  artifacts that expose neither tokens nor reported totals (e.g. SWE-bench
  Verified OpenHands submissions). Both cost fields MUST be null on every row;
  the report suppresses Pareto and per-success cost columns; `analyze()` sets
  `pareto_status="suppressed_cost_not_available"`; `decision_impact` cannot
  return `hedge_on_cost`.

Never fabricate cost (zeros, stale price tables) to dodge `cost_not_available`.
