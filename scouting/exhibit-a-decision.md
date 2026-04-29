# Exhibit A — Decision

**Decided:** 2026-05-02

> Once written, this document is the contract the reanalysis consumes. Locked fields (chosen Exhibit A, column mapping, cost classification, candidate claim) MUST NOT be edited in place without an explicit follow-up note explaining the trigger.

---

## Decision

**Exhibit A: `gaia` (HAL Generalist Agent runs)**

Selected over `tau-bench` (also passing all gates) because GAIA's cost reconciliation is `reconciled` (MAPE = 0.0) while TAU-bench's is `as_reported_only` (MAPE = 0.33), and the design's tiebreaker prefers cleaner cost provenance for the first reanalysis. TAU-bench is retained as a strong secondary candidate; its cost reconciliation failure is a separate scouting lesson worth a follow-up writeup, not the headline of Exhibit A.

`browsecomp` selected as the non-HAL fallback per the design's open question. It fails gate 1 (no public run-level data) and is therefore ineligible as Exhibit A; it is included in this document because the design requires recording all candidates' gate outcomes even when they fail.

---

## Gate matrix

| Candidate     | Gate 1: run-level | Gate 2: claim | Gate 3: cost | Gate 4: collaboration | All pass | Cost classification |
|---------------|---|---|---|---|---|---|
| **gaia**      | PASS | PASS | PASS | PASS | **YES** | `reconciled` (MAPE=0.0) |
| tau-bench     | PASS | PASS | PASS | PASS | YES | `as_reported_only` (MAPE=0.33) |
| browsecomp    | FAIL | FAIL | FAIL | pass-with-caveat | NO | `not_applicable` |

Per-gate evidence is tracked in [.scout-cache/gate_matrix.json](../.scout-cache/gate_matrix.json) (local-only, not committed) and reproducible from the per-candidate fixtures under [scouting/candidates/](candidates/).

---

## Locked fields (contract for `v0-exhibit-a-reanalysis`)

### Exhibit A: GAIA — column mapping

The next change SHALL inherit this column-to-semantic-role mapping for the GAIA per_task table without redeciding any of it. Source of truth: [scouting/candidates/gaia/columns.json](candidates/gaia/columns.json).

| raw_name              | semantic_role           | notes                                          |
|-----------------------|-------------------------|------------------------------------------------|
| `agent_id`            | `agent_id`              |                                                |
| `model_id`            | `model_id`              |                                                |
| `run_id`              | `run_id`                |                                                |
| `task_id`             | `task_id`               | UUID from gaia-benchmark/GAIA validation set   |
| `score_raw`           | `partial_credit`        | JSON-encoded bool/int/null                     |
| `success_bool`        | `success`               | derived: bool score                            |
| `outcome_status`      | `outcome_status`        | `graded` \| `errored`                          |
| `tokens_in_by_model`  | `tokens_in_by_model`    | JSON-encoded per-model breakdown               |
| `tokens_out_by_model` | `tokens_out_by_model`   | JSON-encoded per-model breakdown               |
| `tokens_in_total`     | `tokens_in`             |                                                |
| `tokens_out_total`    | `tokens_out`            |                                                |
| `latency_total_s`     | `latency_s`             |                                                |
| `first_call_ts`       | `timestamp`             | ISO 8601 UTC                                   |
| `last_call_ts`        | `timestamp`             | ISO 8601 UTC                                   |
| `run_total_cost_usd`  | `cost_usd`              | aggregate; per-task cost reconstructed below   |
| `git_commit`          | `rerun_metadata`        |                                                |

### Cost classification

`reconciled` (MAPE = 0.0). HAL's stored `total_cost` matches reconstruction from `tokens_in_by_model` × prices for o4-mini ($1.10/$4.40 per M) and Claude 3.7 Sonnet ($3.00/$15.00 per M) plus gpt-4o ($2.50/$10.00 per M for the judge). Per-task cost is NOT stored upstream — the v0 toolkit MUST reconstruct it from `tokens_in_by_model` × prices, and the toolkit's `cost_usd` semantic role MUST distinguish `reconstructed_per_task_cost_usd` (computed) from `reported_run_total_cost_usd` (HAL's aggregate).

### Candidate claim (verbatim from provenance)

> On GAIA validation, HAL Generalist with o4-mini High (54.5%) and HAL Generalist with Claude 3.7 Sonnet (56.4%) differ by 1.9 percentage points; Claude is 2.2x more expensive ($130.68 vs $59.39). The reanalysis asks whether the 1.9 pp accuracy advantage is statistically distinguishable from noise on n=165, and whether it is decision-relevant given the cost gap.

- **treatment:** `gaia_hg_claude37` (HAL Generalist · Claude 3.7 Sonnet)
- **control:** `gaia_hg_o4mini_high` (HAL Generalist · o4-mini High)
- **outcome:** `success_rate`
- **n_per_arm:** 165 (one full GAIA validation pass per agent)

This claim is **paraphrased** from the GAIA leaderboard rows on hal.cs.princeton.edu/gaia, not verbatim from a published paper.

---

## Residual risks

1. **Single-run-per-agent on HAL.** GAIA exposes one run per (agent, model) — there are no published seed-replications for the chosen pair. The reanalysis will treat task as the unit and use task-level bootstrap to express uncertainty. This is methodologically defensible but should be called out: we cannot disentangle agent-skill variance from run-to-run variance without additional reruns, and HAL traces do not provide them.

2. **Per-task difficulty Level metadata is upstream-gated.** GAIA tasks have Levels 1/2/3 in the source `gaia-benchmark/GAIA` dataset (gated on Hugging Face), but HAL's `raw_eval_results` drops the field. Stratified per-level analysis requires re-joining the gated dataset. The toolkit should make this join first-class rather than hidden.

3. **HAL traces may regenerate.** The `agent-evals/hal_traces` Hugging Face dataset is updated as new agents are uploaded. The two zips selected for Exhibit A (`gaia_hal_generalist_agent_o4mini20250416_high_1745167285_UPLOAD.zip` and `gaia_hal_generalist_agent_claude37sonnet20250219_1744772193_UPLOAD.zip`) are pinned by filename in [scouting/candidates/gaia/provenance.json](candidates/gaia/provenance.json). If those filenames change, the next change MUST detect the drift and either re-pin or open a follow-up scout.

4. **Within-harness only.** The Exhibit A claim compares two models WITHIN the HAL Generalist agent harness on GAIA. Cross-harness comparisons (HAL Generalist vs HF Open Deep Research, or HAL Generalist on GAIA vs Tool Calling on TAU-bench) are out of scope for v0 — the cross-harness confound observed during scouting (Claude 3.7 Sonnet at 56% under HAL Generalist vs 44% under Tool Calling on TAU-bench) is the exact reason.

5. **Reanalysis inherits HAL's sampling decisions.** HAL ran o4-mini at `reasoning_effort=high` and Claude 3.7 Sonnet at default. The reanalysis cannot disentangle "reasoning effort" from "model" within this Exhibit A; this is documented but not corrected.

---

## Synthesised known-truth study

Independent of the public-data choice, [scouting/synthetic/](synthetic/) contains a deterministic 1,200-row dataset (4 agents × 60 tasks × 5 seeds) with known truth for stats-engine validation. The next change SHALL run its analysis pipeline against this dataset before applying it to GAIA, and SHALL assert recovery of:

- Per-agent expected success rate within ±10 percentage points (cluster-aware tolerance, not a binomial CI)
- Pairwise true-effect ranking
- Pareto frontier membership (`agent_a_strong`, `agent_b_strong_close`, `agent_c_mid` — `agent_d_weak` is dominated)
- Holm-Bonferroni non-significance of the primary pair (`agent_a_strong` vs `agent_b_strong_close`, true delta = 0.012)

---

## TAU-bench retained as secondary candidate

TAU-bench Tool Calling passes all four gates and remains a strong secondary candidate for v1+ work, with its own claim already drafted in [scouting/candidates/tau-bench/provenance.json](candidates/tau-bench/provenance.json). The notable findings from TAU-bench scouting that should appear as project lessons (not Exhibit A's headline):

- **Cross-harness confound.** Claude 3.7 Sonnet appears at 56% under HAL Generalist (TAU-bench) and at 44% under Tool Calling — a 12pp scaffold effect. Leaderboards mix both.
- **Cost reconciliation failure.** TAU-bench reported costs cannot be reconstructed from public token counts and prices; reconstructed costs differ from HAL's stored `total_cost` in opposite directions across agents (o4-mini lower, o3 higher). Likely causes: prompt-caching discounts (o4-mini) and stale price snapshots (o3 at pre-2025-06-10 prices).
- **Errored-vs-failed distinction.** Tool Calling Claude 3.7 Sonnet errored on 3/50 tasks; the leaderboard's headline accuracy folds errors into failures.

These belong in a follow-up writeup or paper appendix, not in Exhibit A's primary narrative.

---

## Immutability

The fields locked above (Exhibit A choice, column mapping, cost classification, candidate claim, residual risks) MUST NOT be edited in place once this document is committed. Changes require a follow-up note that explicitly references this decision and explains the trigger. This is a convention, not a CI check; rely on git history to enforce it.
