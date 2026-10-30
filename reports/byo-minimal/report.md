## Audit Summary

- **Verdict:** `switch` — Treatment beat control significantly (the adjusted p-value rejects the null at the declared α) and in the direction the claim predicts. The data supports the claim. Action: switch the default selection to the treatment, subject to cost acceptance.
- **Claim status:** supported
- **Why:** delta +40.00 pp with bootstrap CI [+10.00 pp, +70.00 pp] over 10 paired tasks; treatment is 2.00x the control's cost
- **What would change it:** ~350 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** no residual-risk document bound to this evidence

## Study

- **id:** `byo-minimal`
- **benchmark:** `byo-minimal`
- **harness:** `byo-minimal`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `summary_seen`
- **claim:** Alice (8/10 = 80%) outperforms Bob (4/10 = 40%) on the toy 10-task BYO benchmark while costing 2x more per task ($0.10 vs $0.05). This worked example demonstrates the canonical input contract; the audit verdict should be unambiguous given the deliberately wide success-rate gap.

## Provenance

- **source_fixture:** `examples/byo-minimal/runs.parquet`
- **source_url:** 
- **retrieved_at:** ``
- **cost_provenance:** `reconciled`

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high | total_cost_usd | cost_per_success_usd |
|---|---:|---:|---:|---:|---:|---:|---:|
| alice | 10 | 0 | 0.8000 | 0.4902 | 0.9433 | $1.00 | $0.12 |
| bob | 10 | 0 | 0.4000 | 0.1682 | 0.6873 | $0.50 | $0.12 |

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| alice_vs_bob | declared_reanalysis | supported | +40.00 pp | +5.00 pp | 0.0368 | switch |

**Copyable summary** — `alice_vs_bob`

Claim `alice_vs_bob` verdict `switch` for `alice` vs `bob`: delta +40.00 pp with bootstrap CI [+10.00 pp, +70.00 pp]; evidence readiness `ready_with_warnings`. Cost note: treatment cost is 2.00x control.

**Verdict explainer** — `alice_vs_bob`

- **First matching branch:** `rejecting_adjusted_p_value_claim_direction` → `switch`
- **Rule path:** The correction-adjusted p-value rejects the null and the effect direction matches the declared claim.
- **Evaluated conditions:** Pareto dominated=False; adjusted-p rejection=True; effect direction matches claim=True; quality CI crosses zero=False; cost gap ratio=100.00%; material cost-gap threshold=10%.
- **Suppressed branches:** none.

**MDE context**

- `alice_vs_bob`: bootstrap CI half-width = 30.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; more paired tasks could improve precision under the variance-fixed assumption.

**Verdict sensitivity** — `alice_vs_bob`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | switch |
| alpha | 0.01 | hedge_on_cost ← flips |
| alpha | 0.10 | switch |
| errored_policy | excluded | switch |
| correction_method | none | switch |
| cost_gap_threshold | 0.05 | switch |
| cost_gap_threshold | 0.20 | switch |

## Robustness Review

| Dimension | Result | Notes |
|---|---|---|
| Multiple-comparison correction | does not survive | verdict flips at α=0.01 |
| Errored-row policy | survives | verdict unchanged when errored rows excluded |
| Cost-threshold sensitivity | survives | verdict unchanged at cost_gap_threshold∈{0.05, 0.20} |
| Target MDE | does not survive | CI half-width 30.00 pp > MDE 5.00 pp; under-resolved |
| Cost provenance | survives | reconciled |

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['alice', 'bob']

All agents are on the frontier; no dominance to report.

## Residual risks

(no residual-risk document supplied with this evidence)

## Reproducibility footer

- **rendered_at:** `1970-01-01T00:00:00+00:00`
- **git_commit:** `6138a03`
- **fixture_sha256:** `687cf4d211662ca65fbbfbdcfdab5349cad2b33b99d02fd8d412645798038c41`
- **bootstrap_seed:** `42`
- **bootstrap_iterations:** `10000`
- **alpha:** `0.05`
- **evidence_readiness:** `ready_with_warnings`
- **check_sha256:** `6d444cf10f378725c7b9dadb6bf5c41709b928ffbe62ffde9601ea260ae92d11`
