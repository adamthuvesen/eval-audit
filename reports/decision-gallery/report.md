## Audit Summary

### Claim `hold_pattern`

- **Verdict:** `hold` — Treatment differs from control significantly, but in the OPPOSITE direction of the claim. The data falsifies the claim's stated direction rather than confirming it. Action: hold the current selection; this evidence does not warrant a switch.
- **Claim status:** unsupported
- **Why:** delta -70.00 pp with bootstrap CI [-100.00 pp, -40.00 pp] over 10 paired tasks; treatment is 0.40x the control's cost
- **What would change it:** ~350 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** no residual-risk document bound to this evidence

### Claim `rerun_more_n_pattern`

- **Verdict:** `rerun_more_n` — The bootstrap CI for the delta crosses zero. The cost-gap rule does not select an arm. Action: collect more paired tasks to improve precision. The target MDE is a separate precision diagnostic and does not determine this verdict.
- **Claim status:** inconclusive
- **Why:** delta +10.00 pp with bootstrap CI [-30.00 pp, +50.00 pp] over 10 paired tasks; treatment is 0.94x the control's cost
- **What would change it:** ~630 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** no residual-risk document bound to this evidence

### Claim `inconclusive_no_action_pattern`

- **Verdict:** `inconclusive_no_action` — The bootstrap CI for the delta is one-sided (does not cross zero), but the correction-adjusted p-value does not reject at α — the audit's declared inference contract requires a significant correction-adjusted test before claiming direction. No dominance or cost-gap rule fires. Action: keep the current selection until additional evidence (more N to tighten the test, or cost data that triggers the cost-gap rule) shifts the picture.
- **Claim status:** inconclusive
- **Why:** delta +40.00 pp with bootstrap CI [+10.00 pp, +70.00 pp] over 10 paired tasks; treatment is 0.67x the control's cost
- **What would change it:** ~350 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** no residual-risk document bound to this evidence

## Study

- **id:** `decision-gallery`
- **benchmark:** `decision-gallery`
- **harness:** `decision-gallery`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `full_seen`
- **claim `hold_pattern`:** Synthetic claim targeting the `hold` verdict. The claim asserts hold_treatment beats hold_control on success_rate. The data is constructed so the paired t-test rejects the null at α=0.05 AND the observed direction is opposite the claim — treatment significantly underperforms control. hold_treatment is cheaper than hold_control so it is not Pareto-dominated, which is what lets the engine reach the `hold` rule branch instead of `drop_from_shortlist`.
- **claim `rerun_more_n_pattern`:** Synthetic claim targeting the `rerun_more_n` verdict. The claim asserts rerun_treatment beats rerun_control on success_rate. The data is constructed with similar per-arm success rates and per-task differences that span both directions, so the bootstrap CI clearly crosses zero and the paired t-test does not reject. Costs differ by ~6.67% of the cheaper arm — below the 10% material threshold — so the engine reaches `rerun_more_n` rather than `hedge_on_cost`.
- **claim `inconclusive_no_action_pattern`:** Synthetic claim targeting the `inconclusive_no_action` verdict. The claim asserts inconc_treatment beats inconc_control on success_rate. The data is constructed so the bootstrap CI is entirely positive (no negative per-task differences), but the paired raw p-value is large enough that Holm-Bonferroni correction across the three-claim family pushes the adjusted p above α=0.05. This is the CI vs adjusted-p disagreement case the verdict was designed for; it is naturally rare and the rationale text describes the verdict as a fallback.

## Provenance

- **source_fixture:** `examples/decision-gallery/runs.parquet`
- **source_url:** 
- **retrieved_at:** ``
- **cost_provenance:** `reconciled`

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high | total_cost_usd | cost_per_success_usd |
|---|---:|---:|---:|---:|---:|---:|---:|
| hold_treatment | 10 | 0 | 0.2000 | 0.0567 | 0.5098 | $0.20 | $0.10 |
| hold_control | 10 | 0 | 0.9000 | 0.5958 | 0.9821 | $0.50 | $0.06 |
| rerun_treatment | 10 | 0 | 0.6000 | 0.3127 | 0.8318 | $0.30 | $0.05 |
| rerun_control | 10 | 0 | 0.5000 | 0.2366 | 0.7634 | $0.32 | $0.06 |
| inconc_treatment | 10 | 0 | 0.8000 | 0.4902 | 0.9433 | $0.40 | $0.05 |
| inconc_control | 10 | 0 | 0.4000 | 0.1682 | 0.6873 | $0.60 | $0.15 |

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| hold_pattern | declared_reanalysis | unsupported | -70.00 pp | +5.00 pp | 0.0040 | hold |
| rerun_more_n_pattern | declared_reanalysis | inconclusive | +10.00 pp | +5.00 pp | 0.6783 | rerun_more_n |
| inconclusive_no_action_pattern | declared_reanalysis | inconclusive | +40.00 pp | +5.00 pp | 0.0736 | inconclusive_no_action |

**Copyable summary** — `hold_pattern`

Claim `hold_pattern` verdict `hold` for `hold_treatment` vs `hold_control`: delta -70.00 pp with bootstrap CI [-100.00 pp, -40.00 pp]; evidence readiness `ready_with_warnings`. Cost note: treatment cost is 0.40x control.

**Verdict explainer** — `hold_pattern`

- **First matching branch:** `rejecting_adjusted_p_value_opposite_direction` → `hold`
- **Rule path:** The correction-adjusted p-value rejects the null, but the effect direction is opposite the declared claim.
- **Evaluated conditions:** Pareto dominated=False; adjusted-p rejection=True; effect direction matches claim=False; quality CI crosses zero=False; cost gap ratio=150.00%; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**Copyable summary** — `rerun_more_n_pattern`

Claim `rerun_more_n_pattern` verdict `rerun_more_n` for `rerun_treatment` vs `rerun_control`: delta +10.00 pp with bootstrap CI [-30.00 pp, +50.00 pp]; evidence readiness `ready_with_warnings`. Cost note: treatment cost is 0.94x control.

**Verdict explainer** — `rerun_more_n_pattern`

- **First matching branch:** `uncertainty_without_material_cost_gap` → `rerun_more_n`
- **Rule path:** The quality interval crosses zero and the cost gap is below the material threshold.
- **Evaluated conditions:** Pareto dominated=False; adjusted-p rejection=False; effect direction matches claim=True; quality CI crosses zero=True; cost gap ratio=6.67%; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**Copyable summary** — `inconclusive_no_action_pattern`

Claim `inconclusive_no_action_pattern` verdict `inconclusive_no_action` for `inconc_treatment` vs `inconc_control`: delta +40.00 pp with bootstrap CI [+10.00 pp, +70.00 pp]; evidence readiness `ready_with_warnings`. Cost note: treatment cost is 0.67x control.

**Verdict explainer** — `inconclusive_no_action_pattern`

- **First matching branch:** `fallback_inconclusive` → `inconclusive_no_action`
- **Rule path:** No dominance, rejection, uncertainty-cost, or under-resolution branch matched.
- **Evaluated conditions:** Pareto dominated=False; adjusted-p rejection=False; effect direction matches claim=True; quality CI crosses zero=False; cost gap ratio=50.00%; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**MDE context**

- `hold_pattern`: bootstrap CI half-width = 30.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; more paired tasks could improve precision under the variance-fixed assumption.
- `rerun_more_n_pattern`: bootstrap CI half-width = 40.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; more paired tasks could improve precision under the variance-fixed assumption.
- `inconclusive_no_action_pattern`: bootstrap CI half-width = 30.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; more paired tasks could improve precision under the variance-fixed assumption.

**Verdict sensitivity** — `hold_pattern`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | hold |
| alpha | 0.01 | hold |
| alpha | 0.10 | hold |
| errored_policy | excluded | hold |
| correction_method | none | hold |
| cost_gap_threshold | 0.05 | hold |
| cost_gap_threshold | 0.20 | hold |

**Verdict sensitivity** — `rerun_more_n_pattern`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | rerun_more_n |
| alpha | 0.01 | rerun_more_n |
| alpha | 0.10 | rerun_more_n |
| errored_policy | excluded | rerun_more_n |
| correction_method | none | rerun_more_n |
| cost_gap_threshold | 0.05 | hedge_on_cost ← flips |
| cost_gap_threshold | 0.20 | rerun_more_n |

**Verdict sensitivity** — `inconclusive_no_action_pattern`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | inconclusive_no_action |
| alpha | 0.01 | hedge_on_cost ← flips |
| alpha | 0.10 | switch ← flips |
| errored_policy | excluded | inconclusive_no_action |
| correction_method | none | switch ← flips |
| cost_gap_threshold | 0.05 | inconclusive_no_action |
| cost_gap_threshold | 0.20 | inconclusive_no_action |

## Robustness Review

### Claim `hold_pattern`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 30.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | survives | reconciled |

### Claim `rerun_more_n_pattern`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | does not survive | verdict flips at cost_gap_threshold=0.05 |
| Target MDE | does not survive | CI half-width 40.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | survives | reconciled |

### Claim `inconclusive_no_action_pattern`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | does not survive | verdict flips at α=0.01, α=0.10, correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 30.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | survives | reconciled |

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['hold_control', 'hold_treatment', 'inconc_treatment', 'rerun_treatment']

Dominated agents: ['inconc_control', 'rerun_control']. Each is dominated by another agent that achieves at least the same success_rate at no greater total_cost_usd.

## Residual risks

(no residual-risk document supplied with this evidence)

## Reproducibility footer

- **rendered_at:** `1970-01-01T00:00:00+00:00`
- **git_commit:** `6138a03`
- **fixture_sha256:** `da29e2bb85aec72f04e37534ac097f97b6fb3a0c5cbc2609e26c7c0662992af6`
- **bootstrap_seed:** `42`
- **bootstrap_iterations:** `10000`
- **alpha:** `0.05`
- **evidence_readiness:** `ready_with_warnings`
- **check_sha256:** `8e96d72a826e02a9263d6aea0b1119ffa06e26f62dcaa669556ec3ad17c87973`
