## Audit Summary

- **Verdict:** `switch` — Treatment beat control significantly (the adjusted p-value rejects the null at the declared α) and in the direction the claim predicts. The data supports the claim. Action: switch the default selection to the treatment, subject to cost acceptance.
- **Claim status:** supported
- **Why:** delta +8.09 pp with bootstrap CI [+2.47 pp, +13.93 pp] over 89 paired tasks; cost provenance is `cost_not_available`; no cost ratio is reported
- **What would change it:** ~28 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** cost provenance is cost_not_available, 5 residual risks inherited from scouting

## Study

- **id:** `terminal-bench-2-mux`
- **benchmark:** `terminal-bench-2`
- **harness:** `terminal-bench-2/mux-public-submission-v1`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `full_seen`
- **claim:** On Terminal-Bench 2.0, the public Mux + GPT-5.3-Codex submission is listed at 74.6% accuracy and the public Mux + Claude Opus 4.6 submission is listed at 66.5% accuracy on the official leaderboard. This audit evaluates whether the observed gap is statistically distinguishable from noise on the paired 89-task universe across five public trials per agent. Cost is suppressed because the selected public result.json artifacts do not expose complete cost_usd values across both submissions.

## Provenance

- **source_fixture:** `examples/terminal-bench-2-mux/runs.parquet`
- **source_url:** https://www.tbench.ai/leaderboard/terminal-bench/2.0
- **retrieved_at:** `2026-05-04T04:51:34Z`
- **price_table_pinned_at:** `2026-05-02`
- **cost_provenance:** `cost_not_available`

### Cost provenance caveat

> ⚠️ Cost provenance: cost_not_available

The upstream artifacts for this study do not expose complete, stable cost fields. Per-task cost cannot be reconstructed with the report's pinned price policy, and no complete per-run reported total is available. Rather than smuggle in zeros, this report **suppresses** every cost-derived view: per-agent `total_cost_usd` and `cost_per_success_usd` columns are omitted from the Per-agent summary, the Cost-quality view (Pareto frontier) is suppressed, and `decision_impact` cannot return `hedge_on_cost` for any claim in this study.

**Cost-suppressed agents:**

- `Mux__GPT-5.3-Codex`
- `Mux__Claude-Opus-4.6`

Cost-related residual risks are inherited from the scouting decision document (see Residual risks below).

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high |
|---|---:|---:|---:|---:|---:|
| Mux__GPT-5.3-Codex | 445 | 0 | 0.7461 | 0.7036 | 0.7843 |
| Mux__Claude-Opus-4.6 | 445 | 0 | 0.6652 | 0.6201 | 0.7074 |

_Cost columns suppressed: cost provenance is `cost_not_available`._

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| mux_gpt53_codex_vs_opus46_submission | declared_reanalysis | supported | +8.09 pp | +5.00 pp | 0.0057 | switch |

**Copyable summary** — `mux_gpt53_codex_vs_opus46_submission`

Claim `mux_gpt53_codex_vs_opus46_submission` verdict `switch` for `Mux__GPT-5.3-Codex` vs `Mux__Claude-Opus-4.6`: delta +8.09 pp with bootstrap CI [+2.47 pp, +13.93 pp]; evidence readiness `ready_with_warnings`. Cost caveat: cost provenance is cost_not_available, so cost-derived views and cost-driven verdict branches are suppressed.

**Verdict explainer** — `mux_gpt53_codex_vs_opus46_submission`

- **First matching branch:** `rejecting_adjusted_p_value_claim_direction` → `switch`
- **Rule path:** The correction-adjusted p-value rejects the null and the effect direction matches the declared claim.
- **Evaluated conditions:** Pareto dominated=False; adjusted-p rejection=True; effect direction matches claim=True; quality CI crosses zero=False; cost gap ratio=n/a; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**MDE context**

- `mux_gpt53_codex_vs_opus46_submission`: bootstrap CI half-width = 5.73 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.

**Verdict sensitivity** — `mux_gpt53_codex_vs_opus46_submission`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | switch |
| alpha | 0.01 | switch |
| alpha | 0.10 | switch |
| errored_policy | excluded | switch |
| correction_method | none | switch |
| cost_gap_threshold | 0.05 | n/a (cost suppressed) |
| cost_gap_threshold | 0.20 | n/a (cost suppressed) |

## Robustness Review

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | n/a | cost-gap threshold not applicable; cost provenance is cost_not_available |
| Target MDE | does not survive | CI half-width 5.73 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | does not survive | cost_not_available — Pareto and cost-per-success suppressed; see Cost provenance caveat |

## Cost-quality view

_Cost-quality view suppressed: cost provenance is `cost_not_available`. See the **Cost provenance caveat** above._

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/terminal-bench-2-mux-decision.md`):

1. **Not a clean model-only effect.** The comparison is between public Mux
   submissions, not two models inside a controlled local experiment. The two
   rows differ by model provider and submission date, and may inherit runtime
   or environment differences not visible in the row-level JSON.

2. **Cost is incomplete, not zero.** Public `result.json` rows expose token
   counts, but `agent_result.cost_usd` is missing or zero-placeholder for many
   treatment rows and only partially populated for the control. The report must
   suppress cost-derived columns, Pareto frontier, and `hedge_on_cost`
   decisions.

3. **Leaderboard confidence intervals are not reused as inference.** The
   official 74.6% and 66.5% rows are useful public context, but the report's
   inference comes from the committed task-level rows and paired analysis.

4. **Five trials per task are public artifacts, not a rerun plan.** The audit
   treats the observed five trials per submission as fixed evidence. It does
   not claim the user can reproduce those exact trials locally.

5. **Terminal execution tasks can have environment-sensitive failures.** The
   public task outcomes are accepted as published, but any deeper causal claim
   about why a task failed would require the full execution traces.

## Reproducibility footer

- **rendered_at:** `2026-05-02T12:00:00+00:00`
- **git_commit:** `snapshot`
- **fixture_sha256:** `0000000000000000000000000000000000000000000000000000000000000000`
- **bootstrap_seed:** `42`
- **evidence_readiness:** `ready_with_warnings`
- **check_sha256:** `0790885e4607c1a43f0d2cdd5933585804881d20f35f85d5d286d8fda3be13ce`
