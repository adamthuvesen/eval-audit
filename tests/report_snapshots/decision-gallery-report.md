## Audit Summary

### Claim `hold_pattern`

- **Verdict:** `hold` — Treatment differs from control significantly, but in the OPPOSITE direction of the claim. The data falsifies the claim's stated direction rather than confirming it. Action: hold the current selection; this evidence does not warrant a switch.
- **Claim status:** unsupported
- **Why:** delta -70.00 pp with bootstrap CI [-100.00 pp, -40.00 pp] over 10 paired tasks; treatment is 0.40x the control's cost
- **What would change it:** ~351 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** none flagged at this stage

### Claim `rerun_more_n_pattern`

- **Verdict:** `rerun_more_n` — The bootstrap CI for the delta crosses zero (no decisive direction), and the cost gap is below the material threshold of 10% of the cheaper arm. Neither side has a clean argument from this evidence. Action: collect more paired tasks before deciding; the current N is under-resolved for the question asked.
- **Claim status:** inconclusive
- **Why:** delta +10.00 pp with bootstrap CI [-30.00 pp, +50.00 pp] over 10 paired tasks; treatment is 0.94x the control's cost
- **What would change it:** ~630 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** none flagged at this stage

### Claim `inconclusive_no_action_pattern`

- **Verdict:** `inconclusive_no_action` — No decision rule fires cleanly: the data is neither significantly directional, Pareto-dominated, nor cost-driven by the threshold. The audit produces no actionable verdict from this evidence. Action: keep the current selection until additional evidence (more N, broader benchmarks, or cost data) shifts the picture.
- **Claim status:** inconclusive
- **Why:** delta +40.00 pp with bootstrap CI [+10.00 pp, +70.00 pp] over 10 paired tasks; treatment is 0.67x the control's cost
- **What would change it:** ~350 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** none flagged at this stage

## Study

- **id:** `decision-gallery`
- **benchmark:** `decision-gallery`
- **harness:** `decision-gallery`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `full_seen`
- **claim:** Synthetic claim targeting the `hold` verdict. The claim asserts hold_treatment beats hold_control on success_rate. The data is constructed so the paired t-test rejects the null at α=0.05 AND the observed direction is opposite the claim — treatment significantly underperforms control. hold_treatment is cheaper than hold_control so it is not Pareto-dominated, which is what lets the engine reach the `hold` rule branch instead of `drop_from_shortlist`.

## Provenance

- **source_fixture:** `scouting/candidates/decision-gallery/sample.parquet`
- **source_url:** 
- **retrieved_at:** ``
- **price_table_pinned_at:** `2026-05-02`
- **cost_provenance:** `n/a`

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

**MDE context**

- `hold_pattern`: bootstrap CI half-width = 30.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.
- `rerun_more_n_pattern`: bootstrap CI half-width = 40.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.
- `inconclusive_no_action_pattern`: bootstrap CI half-width = 30.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.

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
| alpha | 0.01 | inconclusive_no_action |
| alpha | 0.10 | switch ← flips |
| errored_policy | excluded | switch ← flips |
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
| Cost provenance | does not survive | n/a |

### Claim `rerun_more_n_pattern`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | survives | verdict unchanged at α∈{0.01, 0.10} and with correction=none |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | does not survive | verdict flips at cost_gap_threshold=0.05 |
| Target MDE | does not survive | CI half-width 40.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | does not survive | n/a |

### Claim `inconclusive_no_action_pattern`

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | does not survive | verdict flips at α=0.10, correction=none |
| Errored-row policy | does not survive | verdict flips when errored rows excluded (inconclusive_no_action → switch) |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 30.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | does not survive | n/a |

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['hold_control', 'hold_treatment', 'inconc_treatment', 'rerun_treatment']

Dominated agents: ['inconc_control', 'rerun_control']. Each is dominated by another agent that achieves at least the same success_rate at no greater total_cost_usd.

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/decision-gallery-decision.md`):

_(no scouting decision document at scouting/decision-gallery-decision.md; residual risks not surfaced.)_

## Reproducibility footer

- **rendered_at:** `2026-05-02T12:00:00+00:00`
- **git_commit:** `snapshot`
- **fixture_sha256:** `0000000000000000000000000000000000000000000000000000000000000000`
- **bootstrap_seed:** `42`
