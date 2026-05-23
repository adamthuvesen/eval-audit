# `eval-audit` study schema

This document is the formal field-by-field reference for `StudySpec`, the declared-study YAML that every `eval-audit` audit consumes alongside its task-level run data. Read this when you are bringing your own data and need to know exactly what shape `eval-audit init`, `validate`, `analyze`, and `report` expect from your `study.yaml`.

The narrative worked example lives in [`examples/byo-minimal/study.yaml`](../../examples/byo-minimal/study.yaml). Open it alongside this doc — it shows the contract in action, with comments explaining each section. The matching `RunRecord` field reference for the run data is at [`agents/docs/INPUT_CONTRACT.md`](INPUT_CONTRACT.md).

> **Doc parity invariant.** The `## Fields` section below and every `## <NestedModel>` sub-section are parsed by `tests/docs/test_study_schema.py` and asserted to match `StudySpec.model_fields` and the corresponding nested-model fields in `eval_audit/schema/study.py`. Add or rename a `### <field>` sub-heading whenever the schema changes, or CI will fail.

## Versioning

`StudySpec` carries a `schema_version` field, defaulting to `1`. Every `study.yaml` that `eval-audit init` scaffolds emits `schema_version: 1` explicitly. Existing YAMLs without the field continue to validate (the default supplies it), but new and scaffolded YAMLs MUST emit it so users see the version stamp inline.

This version of `eval-audit` only supports `schema_version=1`. A future major break in the contract will raise the accepted set; until then, any other value fails validation with an error that names both the field and the offending value.

## Fields

Every `study.yaml` MUST populate every required field listed below. Optional fields can be omitted or set to `null`. Fields marked *used by analysis* affect the audit verdict; fields marked *declarative only* are validated but do not directly drive the engine.

### schema_version

- **Type:** `int` (default `1`)
- **Used by analysis:** no (versioning metadata).
- **BYO guidance:** emit `schema_version: 1` explicitly even though the default supplies it. This version of `eval-audit` rejects any value other than `1`. The field exists so future schema breaks can migrate cleanly.

### id

- **Type:** `str` (required, non-null)
- **Used by analysis:** yes — appears in the rendered report's Study section and in the snapshot file names.
- **BYO guidance:** a stable kebab-case identifier (e.g., `byo-minimal`, `my-study`). When `eval-audit init <name>` scaffolds a study, this value is derived from `<name>`.

### benchmark

- **Type:** `str` (required, non-null)
- **Used by analysis:** yes — appears in the rendered report's Study section and disambiguates studies that target different benchmark families.
- **BYO guidance:** any short identifier naming the benchmark or task family (e.g., `gaia`, `tau_bench`, `byo-minimal`).

### analysis_mode

- **Type:** `Literal["preregistered", "declared_reanalysis", "exploratory"]` (required)
- **Used by analysis:** yes — affects `comparison_family` interpretation and the rendered report's framing.
- **BYO guidance:** `declared_reanalysis` for re-running a known benchmark with a fixed claim; `exploratory` for hypothesis-generating work; `preregistered` for studies registered before observing data.

### data_observation

- **Type:** `Literal["unseen", "summary_seen", "full_seen"]` (required)
- **Used by analysis:** no (declarative only).
- **BYO guidance:** how much you saw of the run data before declaring the claim. `unseen` is strongest; `full_seen` is post-hoc reanalysis. Used by the report to surface researcher degrees of freedom.

### harness

- **Type:** `str` (required, non-null)
- **Used by analysis:** yes — `eval-audit` refuses cross-harness comparisons. Every `RunRecord` in the audit MUST have a `harness` field matching this value. `CrossHarnessComparisonError` applies when treatment and control harnesses differ; `AnalysisInputError` covers missing rows, per-agent harness mismatch, or rows that do not match `study.harness`.
- **BYO guidance:** a stable string naming the scaffold or agent framework. For BYO data, often the same as `benchmark`.

### primary_outcome

- **Type:** `PrimaryOutcome` object (required) — see the `## PrimaryOutcome` section below.
- **Used by analysis:** yes — declares the headline metric and direction.
- **v0 constraint:** `primary_outcome.name` MUST be `"success_rate"`, `primary_outcome.unit` MUST be `"task"`, and `primary_outcome.direction` MUST be `"higher_is_better"`. Other outcome shapes fail validation in v0.

### agents

- **Type:** `list[AgentRef]` (required, non-empty) — see the `## AgentRef` section below.
- **Used by analysis:** yes — declares which agent IDs are valid claim treatments and controls. Every `RunRecord.agent_id` referenced in a claim MUST appear here.
- **BYO guidance:** list every agent that participates in any claim. The `id` strings are pass-throughs from the run data — they MUST match `RunRecord.agent_id` byte-for-byte.

### design

- **Type:** `Design` object (required) — see the `## Design` section below.
- **Used by analysis:** declarative; surfaced in the rendered report's Study section.
- **BYO guidance:** describes how the run data was produced (sampling, replication strategy, rerun policy).

### inference

- **Type:** `Inference` object (required) — see the `## Inference` section below.
- **Used by analysis:** yes — drives multiple-comparison correction, alpha, and resolution planning.
- **BYO guidance:** declares the analysis plan. `correction_method` and `comparison_family` together pick which family-wise correction the report applies.

### cost

- **Type:** `CostConfig` object (required) — see the `## CostConfig` section below.
- **Used by analysis:** yes — drives the cost-quality view (Pareto frontier).
- **v0 constraint:** `cost.primary_view` MUST be `"pareto_frontier"`. `cost.metrics` MUST be a subset of `{reconstructed_per_task_cost_usd, reported_run_total_cost_usd, cost_per_success_usd}`.

### claims

- **Type:** `list[Claim]` (required, non-empty) — see the `## Claim` section below.
- **Used by analysis:** yes — each claim drives one paired-task analysis and one row in the Claims table of the rendered report.
- **BYO guidance:** declare every claim you want the audit to evaluate. Every claim's `treatment` and `control` MUST be agent IDs listed in `agents`. Every claim's `outcome` MUST equal `primary_outcome.name`. Claim IDs MUST be unique within a study.

## PrimaryOutcome

The headline metric the study evaluates.

### name

- **Type:** `str` (required, non-null)
- **v0 constraint:** MUST be `"success_rate"`.

### unit

- **Type:** `Literal["task"]` (required)
- **v0 constraint:** MUST be `"task"` because the engine performs task-level paired analysis.

### direction

- **Type:** `Literal["higher_is_better", "lower_is_better"]` (required)
- **v0 constraint:** MUST be `"higher_is_better"`.

## AgentRef

A reference to one agent participating in the study.

### id

- **Type:** `str` (required, non-null)
- **BYO guidance:** must match `RunRecord.agent_id` byte-for-byte for every row produced by this agent.

## Design

How the run data was produced.

### task_sampling

- **Type:** `str` (required, non-null)
- **BYO guidance:** describes the task universe and sampling rule (e.g., `fixed_public_validation_set`).

### run_strategy

- **Type:** `str` (required, non-null)
- **BYO guidance:** describes how runs were collected (e.g., `observed_public_runs`).

### observed_runs_per_agent

- **Type:** `int` (required, MUST be ≥ 1)
- **BYO guidance:** number of runs per agent that the audit observes. v1 expects the same value across agents.

### rerun_policy

- **Type:** `str` (required, non-null)
- **BYO guidance:** declared policy for reruns (e.g., `recommend_if_decision_sensitive`). Declarative only.

## Inference

The declared analysis plan.

### alpha

- **Type:** `float` (default `0.05`)
- **BYO guidance:** must be strictly between 0 and 1. The Robustness Review perturbs this between `{0.01, 0.10}` to test verdict stability.

### correction_method

- **Type:** `Literal["holm_bonferroni", "benjamini_hochberg"]` (required)
- **BYO guidance:** Holm-Bonferroni for confirmatory `declared_claims`; Benjamini-Hochberg for `exploratory` claim families.

### comparison_family

- **Type:** `Literal["declared_claims", "exploratory"]` (required)
- **BYO guidance:** must align with the chosen `correction_method` (`declared_claims` ↔ `holm_bonferroni`, `exploratory` ↔ `benjamini_hochberg` is the recommended pairing).

### target_mde

- **Type:** `float | None` (optional, MUST be > 0 and <= 1 when declared)
- **BYO guidance:** the smallest effect size the study is powered to detect, in the units of `primary_outcome`. When declared, the Audit Summary's "what would change it" line carries a concrete additional-N estimate; when omitted, the line says no MDE was declared.

## CostConfig

How costs are summarized in the cost-quality view.

### metrics

- **Type:** `list[str]` (required, non-empty)
- **v0 constraint:** every entry MUST be in `{reconstructed_per_task_cost_usd, reported_run_total_cost_usd, cost_per_success_usd}`.
- **BYO guidance:** the cost columns the report should surface. Most BYO studies use just `reconstructed_per_task_cost_usd`.

### primary_view

- **Type:** `Literal["pareto_frontier"]` (required)
- **v0 constraint:** MUST be `"pareto_frontier"`. Other views are deferred.

## Claim

One paired-task comparison the audit evaluates.

### id

- **Type:** `str` (required, non-null, MUST be unique within a study)
- **BYO guidance:** a stable kebab-case identifier per claim (e.g., `alice_vs_bob`).

### text

- **Type:** `str` (required, non-null)
- **BYO guidance:** the human-readable claim sentence. Surfaced verbatim in the rendered report's Claims table and Study section. Use enough detail that a reader can understand the claim without opening the run data.

### treatment

- **Type:** `str` (required, non-null)
- **BYO guidance:** an agent ID listed in `agents`. MUST differ from `control`.

### control

- **Type:** `str` (required, non-null)
- **BYO guidance:** an agent ID listed in `agents`. MUST differ from `treatment`.

### outcome

- **Type:** `str` (required, non-null)
- **v0 constraint:** MUST be `"success_rate"` and MUST equal `primary_outcome.name`.

## Constraints worth knowing

- `schema_version` MUST be `1` in this version of `eval-audit`.
- `agents` and `claims` MUST be non-empty.
- `primary_outcome.name == "success_rate"`, `primary_outcome.unit == "task"`, and `primary_outcome.direction == "higher_is_better"` in v0.
- `inference.target_mde` MUST be `> 0` and `<= 1` when declared.
- Every `Claim.outcome` MUST equal `primary_outcome.name`.
- Every claim's `treatment` and `control` MUST be agent IDs listed in `agents`, and they MUST differ from each other.
- Claim IDs MUST be unique within a study.
- `cost.primary_view == "pareto_frontier"` in v0.
- `cost.metrics` MUST be a subset of the v0 supported set (`reconstructed_per_task_cost_usd`, `reported_run_total_cost_usd`, `cost_per_success_usd`).

The YAML loader aggregates every violation in a single error rather than failing on the first.

## Where to go next

- [`examples/byo-minimal/study.yaml`](../../examples/byo-minimal/study.yaml) — the smallest valid `StudySpec` declaration.
- [`agents/docs/INPUT_CONTRACT.md`](INPUT_CONTRACT.md) — `RunRecord` field-by-field reference for the run data side of the contract.
- The schema source of truth lives in [`eval_audit/schema/study.py`](../../eval_audit/schema/study.py).
