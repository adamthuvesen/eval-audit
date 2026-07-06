# TAU-bench Airline Tool Calling Decision

**Decided:** 2026-05-02

> This document is the contract the rendered TAU-bench Airline Tool Calling report consumes. Locked fields (TAU-bench Airline + Tool Calling harness, three Tool Calling agents, `as_reported_only` cost classification, three pairwise claims) MUST NOT be edited in place without an explicit follow-up note explaining the trigger.

---

## Decision

**TAU-bench Airline Tool Calling: `tau_bench` (HAL TAU-bench Airline · Tool Calling harness)**

Selected as the second reanalysis to exercise the `as_reported_only` cost-provenance branch end-to-end and to surface the project's strongest scouting finding (the cross-harness scaffold confound) as testable data rather than a footnote. Three Tool Calling Airline runs (o4-mini High, Claude 3.7 Sonnet, o3 Medium) on the same 50-task set, three pairwise claims, Holm-Bonferroni over the family of three.

The finding lives in [reports/cross-harness-confound/notes.md](../reports/cross-harness-confound/notes.md) and the rendered reanalysis at [reports/tau-bench-airline-tool-calling/report.md](../reports/tau-bench-airline-tool-calling/report.md).

---

## Locked fields (contract for the rendered report)

| Field | Locked value |
|---|---|
| Benchmark slug (study) | `tau_bench` |
| Scouting fixture dir | `scouting/candidates/tau-bench/` |
| Harness | `tau_bench_tool_calling` |
| Cost provenance | `as_reported_only` (MAPE = 0.33; reconstruction divergent across agents) |
| Agents | `Taubench ToolCalling (o4-mini-2025-04-16 high)`, `Taubench ToolCalling (claude-3.7-sonnet)`, `Taubench ToolCalling (o3-2025-04-16)` |
| Task set | 50 TAU-bench Airline tasks per agent |
| Errored Claude rows | 3/50 (counted as failures in success-rate denominator per the errored-row policy) |

---

## Residual risks

1. **Cost is `as_reported_only` and the per-task estimate is coarse.** HAL's reported run-total cost is used directly; per-task cost reconstruction from `tokens_in_by_model × pinned prices` does not reconcile to the reported total within the toolkit's 1% tolerance. The renderer's Provenance section surfaces the per-run divergences and caveats from [scouting/candidates/tau-bench/cost-reconciliation.json](candidates/tau-bench/cost-reconciliation.json) verbatim. The `cost_per_success_usd` value is `reported_run_total_cost_usd / successes`, a coarser estimate than GAIA HAL Generalist's reconstructed per-task figure.

2. **Cross-harness scaffold confound (the project's strongest scouting finding).** Within TAU-bench Airline, Claude 3.7 Sonnet sits at 56% under the HAL Generalist Agent harness and at 44% under the Tool Calling harness, a 12 percentage point gap on the same model and the same benchmark. The toolkit's `analyze()` refuses cross-harness comparisons (`CrossHarnessComparisonError`); the writeup at [reports/cross-harness-confound/notes.md](../reports/cross-harness-confound/notes.md) makes the finding explicit using TAU-bench Airline Tool Calling's Tool Calling number as data and the upstream leaderboard's HAL Generalist number as a citation. The 12 pp gap is best read as scaffold effect coexisting with sampling-decision drift the leaderboard does not separate.

3. **Errored vs failed are structurally distinct, denominator-collapsed.** TAU-bench Airline grades 50 tasks per run; some return error strings instead of a graded reward. Within Tool Calling, Claude 3.7 Sonnet has 3/50 errored rows. The leaderboard's headline "44%" folds those errored rows in as failures, and the toolkit does the same at the `analyze()` level so paired-task sets stay aligned across arms. The `n_errored` column in the per-agent summary preserves the structural distinction so a reader can always see "this agent's 44% includes 3 upstream errors that the harness could not grade."

4. **Sample costs do not match leaderboard costs precisely.** o4-mini reports $8.38 in the sample vs $11.36 on the leaderboard; o3 Medium reports $32.24 vs $14.56. The leaderboard appears to publish a curated or averaged figure rather than the per-trace cost. The toolkit reports the per-trace cost (HAL's reported run-total) and surfaces the divergence in the Provenance caveat block; that is the honest answer given `as_reported_only`.

5. **Single-run-per-agent on HAL.** Like GAIA HAL Generalist, TAU-bench exposes one run per (agent, model). The reanalysis treats task as the unit and uses task-level paired-cluster bootstrap to express uncertainty. We cannot disentangle agent-skill variance from run-to-run variance without additional reruns, and HAL traces do not provide them.

6. **HAL traces may regenerate.** The `agent-evals/hal_traces` Hugging Face dataset updates as new agents are uploaded. The three zips selected for TAU-bench Airline Tool Calling are pinned by filename in [scouting/candidates/tau-bench/provenance.json](candidates/tau-bench/provenance.json). If those filenames change, the next change MUST detect the drift and either re-pin or open a follow-up scout.

---

## Source of truth

The structural facts above are derived from [scouting/candidates/tau-bench/provenance.json](candidates/tau-bench/provenance.json) (`scouting_lessons` block, `leaderboard_cross_check` array) and [scouting/candidates/tau-bench/cost-reconciliation.json](candidates/tau-bench/cost-reconciliation.json). A future scouting refresh that updates either JSON file MUST also update this document.

---

## Immutability

This document is part of the locked contract for the rendered TAU-bench Airline Tool Calling report. Edits require a follow-up note naming the field being changed and the reason.
