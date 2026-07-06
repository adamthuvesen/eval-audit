## Audit Summary

### Claim `o4mini_vs_claude`

- **Verdict:** `hedge_on_cost` — The bootstrap CI for the delta crosses zero (no quality decision is available), but the cost gap is material (≥10% of the cheaper arm's cost). The decision pivots on cost preference rather than measured quality. Action: pick the cheaper arm unless the (statistically indistinguishable) quality difference matters to your use case.
- **Claim status:** inconclusive
- **Why:** delta +12.00 pp with bootstrap CI [-6.00 pp, +28.00 pp] over 50 paired tasks; treatment is 0.54x the control's cost
- **What would change it:** ~528 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** errored rows present (3 across 1 agent), cost provenance is as_reported_only, 6 residual risks inherited from scouting

### Claim `o4mini_vs_o3`

- **Verdict:** `hedge_on_cost` — The bootstrap CI for the delta crosses zero (no quality decision is available), but the cost gap is material (≥10% of the cheaper arm's cost). The decision pivots on cost preference rather than measured quality. Action: pick the cheaper arm unless the (statistically indistinguishable) quality difference matters to your use case.
- **Claim status:** inconclusive
- **Why:** delta +2.00 pp with bootstrap CI [-12.05 pp, +18.00 pp] over 50 paired tasks; treatment is 0.26x the control's cost
- **What would change it:** ~402 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** errored rows present (3 across 1 agent), cost provenance is as_reported_only, 6 residual risks inherited from scouting

### Claim `claude_vs_o3`

- **Verdict:** `drop_from_shortlist` — Treatment is Pareto-dominated on the cost-quality frontier — another agent achieves equal-or-better quality at equal-or-lower cost. No quality argument can rescue a dominated point. Action: drop the treatment from the shortlist before deciding among the rest.
- **Claim status:** inconclusive
- **Why:** delta -10.00 pp with bootstrap CI [-26.00 pp, +6.00 pp] over 50 paired tasks; treatment is 0.48x the control's cost
- **What would change it:** ~463 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** errored rows present (3 across 1 agent), cost provenance is as_reported_only, 6 residual risks inherited from scouting

## Study

- **id:** `tau-bench-airline-tool-calling`
- **benchmark:** `tau_bench`
- **harness:** `tau_bench_tool_calling`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `summary_seen`
- **claim `o4mini_vs_claude`:** Within TAU-bench Airline under the Tool Calling harness, the leaderboard reports o4-mini High at 56% and Claude 3.7 Sonnet at 44% (folding errored rows in as failures). This reanalysis evaluates whether that 12 percentage point gap is statistically distinguishable from noise on n=50 paired tasks and whether it is decision-relevant given the 1.8x cost gap ($8.38 vs $15.45).
- **claim `o4mini_vs_o3`:** Within TAU-bench Airline under the Tool Calling harness, the leaderboard reports o4-mini High at 56% and o3 Medium at 54%. This reanalysis evaluates whether that 2 percentage point gap supports a model-selection decision once uncertainty and the 3.8x cost gap ($8.38 vs $32.24) are shown.
- **claim `claude_vs_o3`:** Within TAU-bench Airline under the Tool Calling harness, Claude 3.7 Sonnet is reported at 44% (with 3 of 50 errored rows folded in as failures) and o3 Medium at 54%. This reanalysis evaluates whether that 10 percentage point gap is statistically distinguishable from noise on n=50 paired tasks and whether it is decision-relevant given the 2.1x cost gap ($15.45 vs $32.24).

## Provenance

- **source_fixture:** `scouting/candidates/tau-bench/sample.parquet`
- **source_url:** https://huggingface.co/datasets/agent-evals/hal_traces
- **retrieved_at:** `2026-05-02T06:43:37.958388+00:00`
- **price_table_pinned_at:** `2026-05-02`
- **cost_provenance:** `as_reported_only`

### Cost provenance caveat

> ⚠️ Cost provenance: as_reported_only

HAL's reported run-total cost is used directly because per-task cost reconstruction from token counts × pinned provider prices does not reconcile to HAL's reported total within the toolkit's 1% tolerance. Per-task cost analyses are therefore unavailable for this study; cost figures below are derived from the reported run-total divided by graded successes.

**Divergences (per run):**

- Taubench ToolCalling (o4-mini-2025-04-16 high) — reported $8.38, reconstructed $11.36 (note: HAL reported $8.38 which is BELOW reconstructed $11.36 (26.2% lower). Likely cause: prompt-caching discount applied at trace time but not visible in raw prompt_tokens. Investigate prompt_tokens_details.cached_tokens in raw_logging_results.)
- Taubench ToolCalling (claude-3.7-sonnet) — reported $15.45, reconstructed $16.93 (note: HAL reported $15.45 which is BELOW reconstructed $16.93 (8.8% lower). Likely cause: prompt-caching discount applied at trace time but not visible in raw prompt_tokens. Investigate prompt_tokens_details.cached_tokens in raw_logging_results.)
- Taubench ToolCalling (o3-2025-04-16) — reported $32.24, reconstructed $14.56 (note: HAL reported $32.24 which is ABOVE reconstructed $14.56 (121.3% higher). Likely cause: trace was costed against an older OpenAI price table (pre-2025-06-10 cuts) even though the run timestamp is later, or a harness-specific surcharge.)

**Caveats:**

- reconstruction error too high; mape=0.3334; downstream cost analysis must use HAL's reported total_cost as-is and propagate uncertainty

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high | total_cost_usd | cost_per_success_usd |
|---|---:|---:|---:|---:|---:|---:|---:|
| Taubench ToolCalling (o4-mini-2025-04-16 high) | 50 | 0 | 0.5600 | 0.4231 | 0.6884 | $8.38 | $0.30 |
| Taubench ToolCalling (claude-3.7-sonnet) | 47 | 3 | 0.4400 | 0.3116 | 0.5769 | $15.45 | $0.70 |
| Taubench ToolCalling (o3-2025-04-16) | 50 | 0 | 0.5400 | 0.4040 | 0.6703 | $32.24 | $1.19 |

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| o4mini_vs_claude | declared_reanalysis | inconclusive | +12.00 pp | +5.00 pp | 0.5471 | hedge_on_cost |
| o4mini_vs_o3 | declared_reanalysis | inconclusive | +2.00 pp | +5.00 pp | 0.7992 | hedge_on_cost |
| claude_vs_o3 | declared_reanalysis | inconclusive | -10.00 pp | +5.00 pp | 0.5471 | drop_from_shortlist |

**Copyable summary** — `o4mini_vs_claude`

Claim `o4mini_vs_claude` verdict `hedge_on_cost` for `Taubench ToolCalling (o4-mini-2025-04-16 high)` vs `Taubench ToolCalling (claude-3.7-sonnet)`: delta +12.00 pp with bootstrap CI [-6.00 pp, +28.00 pp]; evidence readiness `ready_with_warnings`. Cost caveat: cost provenance is as_reported_only, so costs come from reported totals rather than reconciled per-task reconstruction.

**Verdict explainer** — `o4mini_vs_claude`

- **First matching branch:** `uncertainty_with_material_cost_gap` → `hedge_on_cost`
- **Rule path:** The quality interval crosses zero and the cost gap meets the material threshold.
- **Evaluated conditions:** Pareto dominated=False; adjusted-p rejection=False; effect direction matches claim=True; quality CI crosses zero=True; cost gap ratio=84.32%; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**Copyable summary** — `o4mini_vs_o3`

Claim `o4mini_vs_o3` verdict `hedge_on_cost` for `Taubench ToolCalling (o4-mini-2025-04-16 high)` vs `Taubench ToolCalling (o3-2025-04-16)`: delta +2.00 pp with bootstrap CI [-12.05 pp, +18.00 pp]; evidence readiness `ready_with_warnings`. Cost caveat: cost provenance is as_reported_only, so costs come from reported totals rather than reconciled per-task reconstruction.

**Verdict explainer** — `o4mini_vs_o3`

- **First matching branch:** `uncertainty_with_material_cost_gap` → `hedge_on_cost`
- **Rule path:** The quality interval crosses zero and the cost gap meets the material threshold.
- **Evaluated conditions:** Pareto dominated=False; adjusted-p rejection=False; effect direction matches claim=True; quality CI crosses zero=True; cost gap ratio=284.69%; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**Copyable summary** — `claude_vs_o3`

Claim `claude_vs_o3` verdict `drop_from_shortlist` for `Taubench ToolCalling (claude-3.7-sonnet)` vs `Taubench ToolCalling (o3-2025-04-16)`: delta -10.00 pp with bootstrap CI [-26.00 pp, +6.00 pp]; evidence readiness `ready_with_warnings`. Cost caveat: cost provenance is as_reported_only, so costs come from reported totals rather than reconciled per-task reconstruction.

**Verdict explainer** — `claude_vs_o3`

- **First matching branch:** `pareto_domination` → `drop_from_shortlist`
- **Rule path:** Treatment is Pareto-dominated before statistical or cost-gap branches are considered.
- **Evaluated conditions:** Pareto dominated=True; adjusted-p rejection=False; effect direction matches claim=False; quality CI crosses zero=True; cost gap ratio=108.70%; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**MDE context**

- `o4mini_vs_claude`: bootstrap CI half-width = 17.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.
- `o4mini_vs_o3`: bootstrap CI half-width = 15.02 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.
- `claude_vs_o3`: bootstrap CI half-width = 16.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.

**Verdict sensitivity** — `o4mini_vs_claude`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | hedge_on_cost |
| alpha | 0.01 | hedge_on_cost |
| alpha | 0.10 | hedge_on_cost |
| errored_policy | excluded | hedge_on_cost |
| correction_method | none | hedge_on_cost |
| cost_gap_threshold | 0.05 | hedge_on_cost |
| cost_gap_threshold | 0.20 | hedge_on_cost |

**Verdict sensitivity** — `o4mini_vs_o3`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | hedge_on_cost |
| alpha | 0.01 | hedge_on_cost |
| alpha | 0.10 | hedge_on_cost |
| errored_policy | excluded | hedge_on_cost |
| correction_method | none | hedge_on_cost |
| cost_gap_threshold | 0.05 | hedge_on_cost |
| cost_gap_threshold | 0.20 | hedge_on_cost |

**Verdict sensitivity** — `claude_vs_o3`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | drop_from_shortlist |
| alpha | 0.01 | drop_from_shortlist |
| alpha | 0.10 | drop_from_shortlist |
| errored_policy | excluded | drop_from_shortlist |
| correction_method | none | drop_from_shortlist |
| cost_gap_threshold | 0.05 | drop_from_shortlist |
| cost_gap_threshold | 0.20 | drop_from_shortlist |

## Robustness Review

### Claim `o4mini_vs_claude`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 17.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | caveat | as_reported_only |

### Claim `o4mini_vs_o3`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 15.02 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | caveat | as_reported_only |

### Claim `claude_vs_o3`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 16.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | caveat | as_reported_only |

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['Taubench ToolCalling (o4-mini-2025-04-16 high)']

Dominated agents: ['Taubench ToolCalling (claude-3.7-sonnet)', 'Taubench ToolCalling (o3-2025-04-16)']. Each is dominated by another agent that achieves at least the same success_rate at no greater total_cost_usd.

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/tau-bench-airline-tool-calling-decision.md`):

1. **Cost is `as_reported_only` and the per-task estimate is coarse.** HAL's reported run-total cost is used directly; per-task cost reconstruction from `tokens_in_by_model × pinned prices` does not reconcile to the reported total within the toolkit's 1% tolerance. The renderer's Provenance section surfaces the per-run divergences and caveats from [scouting/candidates/tau-bench/cost-reconciliation.json](candidates/tau-bench/cost-reconciliation.json) verbatim. The `cost_per_success_usd` value is `reported_run_total_cost_usd / successes`, a coarser estimate than GAIA HAL Generalist's reconstructed per-task figure.

2. **Cross-harness scaffold confound (the project's strongest scouting finding).** Within TAU-bench Airline, Claude 3.7 Sonnet sits at 56% under the HAL Generalist Agent harness and at 44% under the Tool Calling harness, a 12 percentage point gap on the same model and the same benchmark. The toolkit's `analyze()` refuses cross-harness comparisons (`CrossHarnessComparisonError`); the writeup at [reports/cross-harness-confound/notes.md](../reports/cross-harness-confound/notes.md) makes the finding explicit using TAU-bench Airline Tool Calling's Tool Calling number as data and the upstream leaderboard's HAL Generalist number as a citation. The 12 pp gap is best read as scaffold effect coexisting with sampling-decision drift the leaderboard does not separate.

3. **Errored vs failed are structurally distinct, denominator-collapsed.** TAU-bench Airline grades 50 tasks per run; some return error strings instead of a graded reward. Within Tool Calling, Claude 3.7 Sonnet has 3/50 errored rows. The leaderboard's headline "44%" folds those errored rows in as failures, and the toolkit does the same at the `analyze()` level so paired-task sets stay aligned across arms. The `n_errored` column in the per-agent summary preserves the structural distinction so a reader can always see "this agent's 44% includes 3 upstream errors that the harness could not grade."

4. **Sample costs do not match leaderboard costs precisely.** o4-mini reports $8.38 in the sample vs $11.36 on the leaderboard; o3 Medium reports $32.24 vs $14.56. The leaderboard appears to publish a curated or averaged figure rather than the per-trace cost. The toolkit reports the per-trace cost (HAL's reported run-total) and surfaces the divergence in the Provenance caveat block; that is the honest answer given `as_reported_only`.

5. **Single-run-per-agent on HAL.** Like GAIA HAL Generalist, TAU-bench exposes one run per (agent, model). The reanalysis treats task as the unit and uses task-level paired-cluster bootstrap to express uncertainty. We cannot disentangle agent-skill variance from run-to-run variance without additional reruns, and HAL traces do not provide them.

6. **HAL traces may regenerate.** The `agent-evals/hal_traces` Hugging Face dataset updates as new agents are uploaded. The three zips selected for TAU-bench Airline Tool Calling are pinned by filename in [scouting/candidates/tau-bench/provenance.json](candidates/tau-bench/provenance.json). If those filenames change, the next change MUST detect the drift and either re-pin or open a follow-up scout.

---

## Reproducibility footer

- **rendered_at:** `2026-07-06T09:02:15.610952+00:00`
- **git_commit:** `acb63d5`
- **fixture_sha256:** `3d8a0434b5ce3eb32735a767758a9c0281148a25e2956dad7d8c886416ffa7b3`
- **bootstrap_seed:** `42`
- **evidence_readiness:** `ready_with_warnings`
- **check_sha256:** `6e6185c7d654d247eb492eeb4ef0c11d819489da49c99efdb1718d133ebf4681`
