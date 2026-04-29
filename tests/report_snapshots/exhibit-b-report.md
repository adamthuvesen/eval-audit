## Study

- **id:** `exhibit-b`
- **benchmark:** `tau_bench`
- **harness:** `tau_bench_tool_calling`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `summary_seen`
- **claim:** Within TAU-bench Airline under the Tool Calling harness, the leaderboard reports o4-mini High at 56% and Claude 3.7 Sonnet at 44% (folding errored rows in as failures). This reanalysis evaluates whether that 12 percentage point gap is statistically distinguishable from noise on n=50 paired tasks and whether it is decision-relevant given the 1.8x cost gap ($8.38 vs $15.45).

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

**MDE context**

- `o4mini_vs_claude`: bootstrap CI half-width = 17.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.
- `o4mini_vs_o3`: bootstrap CI half-width = 16.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.
- `claude_vs_o3`: bootstrap CI half-width = 16.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['Taubench ToolCalling (o4-mini-2025-04-16 high)']

Dominated agents: ['Taubench ToolCalling (claude-3.7-sonnet)', 'Taubench ToolCalling (o3-2025-04-16)']. Each is dominated by another agent that achieves at least the same success_rate at no greater total_cost_usd.

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/exhibit-a-decision.md`):

1. **Single-run-per-agent on HAL.** GAIA exposes one run per (agent, model) — there are no published seed-replications for the chosen pair. The reanalysis will treat task as the unit and use task-level bootstrap to express uncertainty. This is methodologically defensible but should be called out: we cannot disentangle agent-skill variance from run-to-run variance without additional reruns, and HAL traces do not provide them.

2. **Per-task difficulty Level metadata is upstream-gated.** GAIA tasks have Levels 1/2/3 in the source `gaia-benchmark/GAIA` dataset (gated on Hugging Face), but HAL's `raw_eval_results` drops the field. Stratified per-level analysis requires re-joining the gated dataset. The toolkit should make this join first-class rather than hidden.

3. **HAL traces may regenerate.** The `agent-evals/hal_traces` Hugging Face dataset is updated as new agents are uploaded. The two zips selected for Exhibit A (`gaia_hal_generalist_agent_o4mini20250416_high_1745167285_UPLOAD.zip` and `gaia_hal_generalist_agent_claude37sonnet20250219_1744772193_UPLOAD.zip`) are pinned by filename in [scouting/candidates/gaia/provenance.json](candidates/gaia/provenance.json). If those filenames change, the next change MUST detect the drift and either re-pin or open a follow-up scout.

4. **Within-harness only.** The Exhibit A claim compares two models WITHIN the HAL Generalist agent harness on GAIA. Cross-harness comparisons (HAL Generalist vs HF Open Deep Research, or HAL Generalist on GAIA vs Tool Calling on TAU-bench) are out of scope for v0 — the cross-harness confound observed during scouting (Claude 3.7 Sonnet at 56% under HAL Generalist vs 44% under Tool Calling on TAU-bench) is the exact reason.

5. **Reanalysis inherits HAL's sampling decisions.** HAL ran o4-mini at `reasoning_effort=high` and Claude 3.7 Sonnet at default. The reanalysis cannot disentangle "reasoning effort" from "model" within this Exhibit A; this is documented but not corrected.

---

## Reproducibility footer

- **rendered_at:** `2026-05-02T12:00:00+00:00`
- **git_commit:** `snapshot`
- **fixture_sha256:** `0000000000000000000000000000000000000000000000000000000000000000`
- **bootstrap_seed:** `42`
