## Audit Summary

- **Verdict:** `switch` — Treatment beat control significantly (the adjusted p-value rejects the null at the declared α) and in the direction the claim predicts. The data supports the claim. Action: switch the default selection to the treatment, subject to cost acceptance.
- **Claim status:** supported
- **Why:** delta +5.80 pp with bootstrap CI [+3.00 pp, +8.80 pp] over 500 paired tasks; cost provenance is `cost_not_available`; no cost ratio is reported
- **What would change it:** the study already resolves below the declared MDE (CI half-width 2.90 pp ≤ MDE 5.00 pp); no additional N would change the verdict
- **Reviewer pushback:** cost provenance is cost_not_available, 5 residual risks inherited from scouting

## Study

- **id:** `swe-bench-verified-openhands`
- **benchmark:** `swe-bench-verified`
- **harness:** `swe-bench-verified/openhands-public-submission-v1`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `full_seen`
- **claim:** On SWE-bench Verified (500 tasks), the public OpenHands + Claude Opus 4.5 submission (20251127_openhands_claude-opus-4-5) resolves 388/500 instances and the public OpenHands + GPT-5 submission (20250807_openhands_gpt5) resolves 359/500. This re-analysis evaluates whether the +5.8 pp headline gap is statistically distinguishable from noise once the paired discordants (45 treatment-only solves vs 16 control-only solves) are surfaced. The submissions differ in OpenHands runtime commit and `max_iterations` budget (500 vs 100); this is a submission-level audit, not a model-only effect.

## Provenance

- **source_fixture:** `examples/swe-bench-verified-openhands/runs.parquet`
- **source_url:** https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/main/data/test-00000-of-00001.parquet
- **retrieved_at:** `2026-05-03T17:40:27Z`
- **price_table_pinned_at:** `2026-05-02`
- **cost_provenance:** `cost_not_available`

### Cost provenance caveat

> ⚠️ Cost provenance: cost_not_available

The upstream artifacts for this study do not expose complete, stable cost fields. Per-task cost cannot be reconstructed with the report's pinned price policy, and no complete per-run reported total is available. Rather than smuggle in zeros, this report **suppresses** every cost-derived view: per-agent `total_cost_usd` and `cost_per_success_usd` columns are omitted from the Per-agent summary, the Cost-quality view (Pareto frontier) is suppressed, and `decision_impact` cannot return `hedge_on_cost` for any claim in this study.

**Cost-suppressed agents:**

- `20251127_openhands_claude-opus-4-5`
- `20250807_openhands_gpt5`

Cost-related residual risks are inherited from the scouting decision document (see Residual risks below).

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high |
|---|---:|---:|---:|---:|---:|
| 20251127_openhands_claude-opus-4-5 | 500 | 0 | 0.7760 | 0.7374 | 0.8104 |
| 20250807_openhands_gpt5 | 500 | 0 | 0.7180 | 0.6770 | 0.7557 |

_Cost columns suppressed: cost provenance is `cost_not_available`._

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| opus45_vs_gpt5_submission | declared_reanalysis | supported | +5.80 pp | +5.00 pp | 0.0002 | switch |

**MDE context**

- `opus45_vs_gpt5_submission`: bootstrap CI half-width = 2.90 pp vs target_mde = 5.00 pp — the study has resolution finer than the declared MDE; an effect of this size would be detectable.

**Verdict sensitivity** — `opus45_vs_gpt5_submission`

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
| Target MDE | survives | CI half-width 2.90 pp ≤ MDE 5.00 pp; sufficiently resolved |
| Cost provenance | does not survive | cost_not_available — Pareto and cost-per-success suppressed; see Cost provenance caveat |

## Cost-quality view

_Cost-quality view suppressed: cost provenance is `cost_not_available`. See the **Cost provenance caveat** above._

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/swe-bench-verified-openhands-decision.md`):

1. **Not a clean model-only effect.** The comparison is between public
   OpenHands submissions. The Opus submission used a different OpenHands path
   (Software Agent SDK + benchmark commit) and 500 max iterations; the GPT-5
   submission cites an OpenHands commit and 100 max iterations. A report must
   say "OpenHands + Opus 4.5 submission vs OpenHands + GPT-5 submission," not
   "Opus 4.5 beats GPT-5."

2. **Cost provenance is unresolved.** Sampled `report.json` files expose patch
   application and test status. Sampled trajectory JSON files expose messages
   and terminal content. A recursive key scan of sampled trajectories found no
   stable `token`, `usage`, or `cost` fields. Do not publish cost/Pareto
   claims from this candidate until this is solved.

3. **Artifact completeness differs.** Treatment has 500 `all_preds` rows but
   only 489 trajectory files and 498 report files. Control has 499 `all_preds`
   rows, 500 trajectory files, and 498 report files. The success-rate audit can
   rely on `results.json`, but any deeper provenance/cost extraction must
   explain missing artifacts.

4. **`no_generation` / `no_logs` semantics need a deliberate mapping.**
   Treatment has 2 `no_generation` and 0 `no_logs`; control has 1
   `no_generation` and 0 `no_logs` in `results.json`. Whether these are
   `graded` failures or `errored` rows should be locked before the report.

5. **SWE-bench submission policy changed after these runs.** The
   `swe-bench/experiments` README notes a 2025-11-18 policy change for
   Verified and Multilingual submissions. The candidate should cite the exact
   submission directories and not imply all historical submissions meet the
   latest acceptance policy.

## Reproducibility footer

- **rendered_at:** `2026-05-02T12:00:00+00:00`
- **git_commit:** `snapshot`
- **fixture_sha256:** `0000000000000000000000000000000000000000000000000000000000000000`
- **bootstrap_seed:** `42`
- **evidence_readiness:** `ready_with_warnings`
- **check_sha256:** `02a72df17ebe744d39650393d6ea387a627ba4221d5e4148ac9d177d446d0e89`
