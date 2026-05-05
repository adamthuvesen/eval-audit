## Audit Summary

- **Verdict:** `inconclusive_no_action` — The bootstrap CI for the delta is one-sided (does not cross zero), but the correction-adjusted p-value does not reject at α — the audit's declared inference contract requires a significant correction-adjusted test before claiming direction. No dominance or cost-gap rule fires. Action: keep the current selection until additional evidence (more N to tighten the test, or cost data that triggers the cost-gap rule) shifts the picture.
- **Claim status:** inconclusive
- **Why:** delta +11.67 pp with bootstrap CI [+1.67 pp, +23.33 pp] over 30 paired tasks; treatment is 2.00x the control's cost
- **What would change it:** ~6 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** 5 residual risks inherited from scouting

## Study

- **id:** `humaneval-direct-completion`
- **benchmark:** `humaneval`
- **harness:** `eval-audit/humaneval-direct-completion-v1`
- **analysis_mode:** `preregistered`
- **data_observation:** `unseen`
- **claim:** On a 30-task HumanEval slice (seed=42) under the `eval-audit/humaneval-direct-completion-v1` thin direct-completion harness with tools disabled and temperature=0, Claude Sonnet 4.6 is compared against Claude Haiku 4.5 on success_rate. The audit asks whether any observed gap is statistically distinguishable from noise on n=30 (target MDE 0.10), and what the cost-quality tradeoff looks like at the price-table date 2026-05-03.

## Provenance

- **mode:** `controlled_original_runs` — predeclared run, paired arms on the same task IDs under one harness; this is original evidence, not public-data reanalysis or a synthetic example.
- **run_plan:** `scouting/humaneval-direct-completion/run-plan.md`
- **decision_doc:** `scouting/humaneval-direct-completion-decision.md`
- **task_source:** `openai/human-eval (MIT)`
- **harness:** `eval-audit/humaneval-direct-completion-v1` at git commit `7cfd9b0`
- **model_arms:**
  - `humaneval-direct-haiku-4-5` → `claude-haiku-4-5-20251001` (2 run(s) per task)
  - `humaneval-direct-sonnet-4-6` → `claude-sonnet-4-6` (2 run(s) per task)
- **rerun_policy:** `capture_provider_nondeterminism`
- **run_dates:** `2026-05-03` to `2026-05-03` (UTC)
- **price_table_pinned_at:** `2026-05-03`
- **cost_provenance:** `partial` (120/120 rows)

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high | total_cost_usd | cost_per_success_usd |
|---|---:|---:|---:|---:|---:|---:|---:|
| humaneval-direct-haiku-4-5 | 60 | 0 | 0.8833 | 0.7782 | 0.9423 | $0.05 | $0.00 |
| humaneval-direct-sonnet-4-6 | 60 | 0 | 1.0000 | 0.9398 | 1.0000 | $0.10 | $0.00 |

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| sonnet46_vs_haiku45_on_humaneval30 | preregistered | inconclusive | +11.67 pp | +10.00 pp | 0.0504 | inconclusive_no_action |

**MDE context**

- `sonnet46_vs_haiku45_on_humaneval30`: bootstrap CI half-width = 10.83 pp vs target_mde = 10.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.

**Verdict sensitivity** — `sonnet46_vs_haiku45_on_humaneval30`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | inconclusive_no_action |
| alpha | 0.01 | inconclusive_no_action |
| alpha | 0.10 | switch ← flips |
| errored_policy | excluded | inconclusive_no_action |
| correction_method | none | inconclusive_no_action |
| cost_gap_threshold | 0.05 | inconclusive_no_action |
| cost_gap_threshold | 0.20 | inconclusive_no_action |

## Robustness Review

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | does not survive | verdict flips at α=0.10 |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 10.83 pp > MDE 10.00 pp; under-resolved |
| Cost provenance | caveat | partial |

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['humaneval-direct-haiku-4-5', 'humaneval-direct-sonnet-4-6']

All agents are on the frontier; no dominance to report.

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/humaneval-direct-completion-decision.md`):

1. **HumanEval is in training data.** Both Haiku 4.5 and Sonnet 4.6 have almost certainly seen HumanEval during pretraining. The audit demonstrates audit methodology, not frontier-capability claims. The report's Residual Risks section calls this out.

2. **Provider non-determinism at temperature=0.** The Anthropic Messages API at temperature=0 is approximately but not strictly deterministic. The 2 reruns capture provider-level run-to-run variance and contribute to the bootstrap CIs. If reruns within an arm disagree on a task, both rows are kept; the existing analysis engine aggregates per task.

3. **No tools, no scaffold.** HumanEval Direct Completion deliberately uses the thinnest possible harness — a single API call per task, no tool use, no agent framework. This is the cleanest possible audit but is not representative of how either model would perform under a richer scaffold. The exhibit is explicitly "controlled original evidence under harness `eval-audit/humaneval-direct-completion-v1`", not a frontier-capability comparison.

4. **Small N.** n=30 tasks gives a target MDE of ~0.10. Effects smaller than 10 percentage points may be detectable only as wide CIs; the report surfaces this in Verdict Sensitivity.

5. **Within-harness only.** Like GAIA HAL Generalist and TAU-bench Airline Tool Calling, this audit compares two arms within ONE harness. Cross-harness comparisons are out of scope by repo policy.

---

## Reproducibility footer

- **rendered_at:** `2026-05-02T12:00:00+00:00`
- **git_commit:** `snapshot`
- **fixture_sha256:** `0000000000000000000000000000000000000000000000000000000000000000`
- **bootstrap_seed:** `42`
