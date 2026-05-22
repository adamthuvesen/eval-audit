# `eval-audit` input contract

This document is the formal field-by-field reference for `RunRecord`, the canonical task-level row that every `eval-audit` audit consumes. Read this when you are bringing your own evaluation data and want to know exactly what `analyze` and `report` expect.

The narrative worked example lives in [`examples/byo-minimal/`](../../examples/byo-minimal/). Open the parquet and the `make_runs.py` script alongside this doc — they show the contract in action.

> **Doc parity invariant.** The `## Fields` section below is parsed by `tests/docs/test_input_contract.py` and asserted to match `RunRecord.model_fields` from `eval_audit/schema/run_record.py`. Add or rename a `### <field>` sub-heading whenever the schema changes, or CI will fail.

## Two ways to feed `eval-audit` data

`eval-audit` accepts run-level data through two deliberately different conventions:

- **Adapter path (existing benchmarks, demos):**

  ```bash
  eval-audit analyze studies/gaia-hal-generalist.yaml
  ```

  Reads from a directory containing auxiliary files such as `sample.parquet`,
  `cost-reconciliation.json`, `columns.json`, and `provenance.json`.

- **BYO path (your data):**

  ```bash
  eval-audit analyze study.yaml --runs path/to/runs.parquet
  ```

  Reads from a single parquet file; no auxiliary files are needed.

The directory convention exists because real benchmark fixtures need provenance, cost reconciliation, and column-mapping receipts. The `--runs <file>` convention is for users whose data is already canonical — they have one parquet, not a directory of receipts.

## Format

- **Parquet only.** Token-breakdown fields (`tokens_in_by_model`, `tokens_out_by_model`) are dicts; CSV does not preserve them cleanly. Convert other formats to parquet via three lines of polars or pandas.
- **Schema is enforced row-by-row** through the canonical `RunRecord` Pydantic model. Errors name the offending row index, field path, and bad value. The original `pydantic.ValidationError` is preserved as the exception's `__cause__` for debug consumers.
- **Row order is unspecified.** Downstream code does not depend on it. Feel free to sort by whatever is convenient.

## Fields

Every row in your parquet must populate every field listed below. Optional fields can be `null`; required fields must be non-null. Fields marked *used by analysis* affect the audit verdict; fields marked *preserved provenance* are validated but not consumed by the headline pipeline.

### agent_id

- **Type:** `str` (required, non-null)
- **Used by analysis:** yes — filters per-agent slices, drives Pareto frontier, joins claim treatment/control to rows.
- **BYO guidance:** any stable identifier. The example uses `"alice"` and `"bob"`.

### model_id

- **Type:** `str` (required, non-null)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** the model name behind the agent, e.g. `"claude-3-7-sonnet-20250219"` or just `"alice"` if your agent identity is the model. Distinct from `agent_id` so a single model can serve multiple harnesses.

### harness

- **Type:** `str` (required, non-null)
- **Used by analysis:** yes — cross-harness comparison refusal. `analyze()` raises `CrossHarnessComparisonError` if a claim's treatment and control run under different harnesses; other harness or missing-row failures raise `AnalysisInputError`.
- **BYO guidance:** all rows in a single audit must share one harness value. Pick a string that names the scaffold (e.g. `"my-harness"`).

### run_id

- **Type:** `str` (required, non-null)
- **Used by analysis:** yes — used to compute `reported_run_total_cost_usd` per (agent, run) when cost provenance is `as_reported_only`.
- **BYO guidance:** identifies one execution of an agent over the task set. If you only have one run per agent, a stable per-agent string works.

### task_id

- **Type:** `str` (required, non-null)
- **Used by analysis:** yes — paired-task analysis joins treatment and control rows on this column.
- **BYO guidance:** must be identical between treatment and control for the same task. Use a stable identifier (e.g. the task's index or hash).

### task_category

- **Type:** `str | None` (optional)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** optional sub-grouping, e.g. `"reasoning"` vs `"factual"`. Use `null` if not applicable.

### seed

- **Type:** `int | None` (optional)
- **Used by analysis:** no in v1.x (replication support is roadmapped for later).
- **BYO guidance:** the random seed used for the run, if any. `null` if your runs are not seed-reproducible.

### success

- **Type:** `bool | None` (required field; null only when `outcome_status="errored"`)
- **Used by analysis:** yes — the headline outcome for the v1 contract (`success_rate` only).
- **BYO guidance:** `True` if the agent solved the task, `False` if it failed. Use `null` when the task errored upstream (`outcome_status="errored"`); the schema will reject `True`/`False` paired with `outcome_status="errored"`.

### partial_credit

- **Type:** `float | int | bool | None` (optional)
- **Used by analysis:** no in v1.x (`partial_credit` as an outcome is roadmapped).
- **BYO guidance:** validated for shape but ignored by analysis. Pass `null`, or `float(success)` if you want a placeholder. Must be `null` when `outcome_status="errored"`.

### outcome_status

- **Type:** `Literal["graded", "errored"]` (required)
- **Used by analysis:** yes — `errored` rows count as failures in the headline denominator and are surfaced in `n_errored`. `graded` rows feed the bootstrap and per-task analysis.
- **BYO guidance:** `"graded"` for normal task outcomes; `"errored"` when the agent's run errored before producing a gradable result. The schema enforces that `outcome_status="graded"` requires non-null `success`, and `outcome_status="errored"` requires `success` and `partial_credit` to be `null`.

### tokens_in

- **Type:** `int >= 0` (required)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** input token count for this task. Use `0` if you don't track tokens.

### tokens_out

- **Type:** `int >= 0` (required)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** output token count for this task. Use `0` if you don't track tokens.

### tokens_in_by_model

- **Type:** `dict[str, int]` (required, may be `{}`)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** per-model breakdown of input tokens, e.g. `{"alice": 1000}`. If you do not track per-model breakdowns, a one-key `{model_id: tokens_in}` dict is fine. Empty `{}` is also accepted.

### tokens_out_by_model

- **Type:** `dict[str, int]` (required, may be `{}`)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** as above for output tokens. One-key dicts and empty dicts both validate.

### latency_s

- **Type:** `float | None` with `>= 0` (optional)
- **Used by analysis:** no in v1.x (`latency_s` as an outcome is roadmapped).
- **BYO guidance:** wall-clock time for the task, in seconds. `null` if not tracked.

### timestamp

- **Type:** `datetime | None` (optional)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** when the task was run. `null` if not tracked.

### reconstructed_per_task_cost_usd

- **Type:** `float | None` with `>= 0` (required when `cost_provenance="reconciled"`, may be `null` otherwise)
- **Used by analysis:** yes — feeds the per-agent total cost and the Pareto frontier when `cost_provenance="reconciled"`.
- **BYO guidance:** the per-task cost reconstructed from token counts × pinned model prices, in USD. Required for `reconciled` provenance. `null` for `as_reported_only` (the schema enforces consistency).

### reported_run_total_cost_usd

- **Type:** `float | None` with `>= 0` (optional)
- **Used by analysis:** yes — used as the cost basis when `cost_provenance="as_reported_only"` (typically equal across all rows of the same `(agent_id, run_id)`).
- **BYO guidance:** the run-level total cost reported by your harness, if available.

### cost_provenance

- **Type:** `Literal["reconciled", "partial", "as_reported_only"]` (required)
- **Used by analysis:** yes — drives the cost-summary code path AND the Robustness Review's "Cost provenance" row.
- **BYO guidance:**
  - `"reconciled"` when your `reconstructed_per_task_cost_usd` agrees with the harness's reported run total within ~1%. Most BYO data is `reconciled` because you control the price table.
  - `"as_reported_only"` when per-task reconstruction does not reconcile and the audit must use the run-level reported total instead.
  - `"partial"` is currently rejected by analysis (mixed null/non-null reconstructed costs would silently undercount); v1 enforces explicit handling.

### rerun_metadata

- **Type:** `dict[str, str]` (required, may be `{}`, default `{}`)
- **Used by analysis:** no (preserved provenance).
- **BYO guidance:** free-form metadata about how this row was produced (source URL, retrieval timestamp, fixture path). Audit reports do not surface these directly but they're preserved for downstream consumers.

## Constraints worth knowing

- `outcome_status="graded"` ⇒ `success` is non-null.
- `outcome_status="errored"` ⇒ `success` and `partial_credit` are both `null`.
- `cost_provenance="reconciled"` ⇒ `reconstructed_per_task_cost_usd` is non-null.
- All numeric fields enforce `>= 0`.
- Dict fields enforce non-negative integer values.

These are checked row-by-row at load time. A failure raises `IngestContractError` naming the offending row index, field path, and bad value.

## Where to go next

- [`examples/byo-minimal/study.yaml`](../../examples/byo-minimal/study.yaml) — the smallest valid `StudySpec` declaration.
- [`examples/byo-minimal/make_runs.py`](../../examples/byo-minimal/make_runs.py) — the construction pattern most BYO users will follow.
- The schema source of truth lives in [`eval_audit/schema/run_record.py`](../../eval_audit/schema/run_record.py).
