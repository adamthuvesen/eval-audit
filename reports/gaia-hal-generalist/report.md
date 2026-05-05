## Audit Summary

- **Verdict:** `hedge_on_cost` — The bootstrap CI for the delta crosses zero (no quality decision is available), but the cost gap is material (≥10% of the cheaper arm's cost). The decision pivots on cost preference rather than measured quality. Action: pick the cheaper arm unless the (statistically indistinguishable) quality difference matters to your use case.
- **Claim status:** inconclusive
- **Why:** delta +1.82 pp with bootstrap CI [-7.27 pp, +10.91 pp] over 165 paired tasks; treatment is 2.20x the control's cost
- **What would change it:** ~1351 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** 5 residual risks inherited from scouting

## Study

- **id:** `gaia-hal-generalist`
- **benchmark:** `gaia`
- **harness:** `hal_generalist_agent`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `summary_seen`
- **claim:** On GAIA validation under the HAL Generalist agent harness, Claude 3.7 Sonnet (56.4%) outperforms o4-mini High (54.5%) by 1.9 percentage points while costing 2.2x more ($130.68 vs $59.39). This reanalysis evaluates whether that 1.9 pp accuracy advantage is statistically distinguishable from noise on n=165, and whether it is decision-relevant given the cost gap.

## Provenance

- **source_fixture:** `scouting/candidates/gaia/sample.parquet`
- **source_url:** https://huggingface.co/datasets/agent-evals/hal_traces
- **retrieved_at:** `2026-05-02T06:50:59.916942+00:00`
- **price_table_pinned_at:** `2026-05-02`
- **cost_provenance:** `reconciled`

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high | total_cost_usd | cost_per_success_usd |
|---|---:|---:|---:|---:|---:|---:|---:|
| HAL Generalist Agent (claude-3-7-sonnet-20250219) | 165 | 0 | 0.5636 | 0.4874 | 0.6370 | $130.68 | $1.41 |
| HAL Generalist Agent (o4-mini-2025-04-16 high) | 165 | 0 | 0.5455 | 0.4693 | 0.6195 | $59.39 | $0.66 |

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| claude37_vs_o4mini_high_on_gaia | declared_reanalysis | inconclusive | +1.82 pp | +3.00 pp | 0.7021 | hedge_on_cost |

**MDE context**

- `claude37_vs_o4mini_high_on_gaia`: bootstrap CI half-width = 9.09 pp vs target_mde = 3.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.

**Verdict sensitivity** — `claude37_vs_o4mini_high_on_gaia`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | hedge_on_cost |
| alpha | 0.01 | hedge_on_cost |
| alpha | 0.10 | hedge_on_cost |
| errored_policy | excluded | hedge_on_cost |
| correction_method | none | hedge_on_cost |
| cost_gap_threshold | 0.05 | hedge_on_cost |
| cost_gap_threshold | 0.20 | hedge_on_cost |

## Robustness Review

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 9.09 pp > MDE 3.00 pp; under-resolved |
| Cost provenance | survives | reconciled |

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['HAL Generalist Agent (claude-3-7-sonnet-20250219)', 'HAL Generalist Agent (o4-mini-2025-04-16 high)']

All agents are on the frontier; no dominance to report.

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/gaia-hal-generalist-decision.md`):

1. **Single-run-per-agent on HAL.** GAIA exposes one run per (agent, model) — there are no published seed-replications for the chosen pair. The reanalysis will treat task as the unit and use task-level bootstrap to express uncertainty. This is methodologically defensible but should be called out: we cannot disentangle agent-skill variance from run-to-run variance without additional reruns, and HAL traces do not provide them.

2. **Per-task difficulty Level metadata is upstream-gated.** GAIA tasks have Levels 1/2/3 in the source `gaia-benchmark/GAIA` dataset (gated on Hugging Face), but HAL's `raw_eval_results` drops the field. Stratified per-level analysis requires re-joining the gated dataset. The toolkit should make this join first-class rather than hidden.

3. **HAL traces may regenerate.** The `agent-evals/hal_traces` Hugging Face dataset is updated as new agents are uploaded. The two zips selected for GAIA HAL Generalist (`gaia_hal_generalist_agent_o4mini20250416_high_1745167285_UPLOAD.zip` and `gaia_hal_generalist_agent_claude37sonnet20250219_1744772193_UPLOAD.zip`) are pinned by filename in [scouting/candidates/gaia/provenance.json](candidates/gaia/provenance.json). If those filenames change, the next change MUST detect the drift and either re-pin or open a follow-up scout.

4. **Within-harness only.** The GAIA HAL Generalist claim compares two models WITHIN the HAL Generalist agent harness on GAIA. Cross-harness comparisons (HAL Generalist vs HF Open Deep Research, or HAL Generalist on GAIA vs Tool Calling on TAU-bench) are out of scope for v0 — the cross-harness confound observed during scouting (Claude 3.7 Sonnet at 56% under HAL Generalist vs 44% under Tool Calling on TAU-bench) is the exact reason.

5. **Reanalysis inherits HAL's sampling decisions.** HAL ran o4-mini at `reasoning_effort=high` and Claude 3.7 Sonnet at default. The reanalysis cannot disentangle "reasoning effort" from "model" within this GAIA HAL Generalist; this is documented but not corrected.

---

## Reproducibility footer

- **rendered_at:** `2026-05-04T04:24:25.419697+00:00`
- **git_commit:** `072e906`
- **fixture_sha256:** `83d4a0ce9d82d23c7563e66e03f50350d245a8537ddc3b2f6a25a3bae9619720`
- **bootstrap_seed:** `42`
