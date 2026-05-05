## Audit Summary

- **Verdict:** `switch` — claim is supported and the effect favours the treatment
- **Claim status:** supported
- **Why:** delta +40.00 pp with bootstrap CI [+10.00 pp, +70.00 pp] over 10 paired tasks; treatment is 2.00x the control's cost
- **What would change it:** ~350 more paired tasks would tighten the CI to ≤ MDE (estimated, variance-fixed scaling)
- **Reviewer pushback:** none flagged at this stage

## Study

- **id:** `byo-minimal`
- **benchmark:** `byo-minimal`
- **harness:** `byo-minimal`
- **analysis_mode:** `declared_reanalysis`
- **data_observation:** `summary_seen`
- **claim:** Alice (8/10 = 80%) outperforms Bob (4/10 = 40%) on the toy 10-task BYO benchmark while costing 2x more per task ($0.10 vs $0.05). This worked example demonstrates the canonical input contract; the audit verdict should be unambiguous given the deliberately wide success-rate gap.

## Provenance

- **source_fixture:** `scouting/candidates/byo-minimal/sample.parquet`
- **source_url:** 
- **retrieved_at:** ``
- **price_table_pinned_at:** `2026-05-02`
- **cost_provenance:** `n/a`

## Per-agent summary

| agent_id | n_graded | n_errored | success_rate | success_rate_ci_low | success_rate_ci_high | total_cost_usd | cost_per_success_usd |
|---|---:|---:|---:|---:|---:|---:|---:|
| alice | 10 | 0 | 0.8000 | 0.4902 | 0.9433 | $1.00 | $0.12 |
| bob | 10 | 0 | 0.4000 | 0.1682 | 0.6873 | $0.50 | $0.12 |

## Claims

| claim_id | mode | status | effect | target_mde | adjusted_result | decision_impact |
|---|---|---|---|---|---|---|
| alice_vs_bob | declared_reanalysis | supported | +40.00 pp | +5.00 pp | 0.0368 | switch |

**MDE context**

- `alice_vs_bob`: bootstrap CI half-width = 30.00 pp vs target_mde = 5.00 pp — the study has resolution coarser than the declared MDE; an effect at the declared MDE would not be reliably detected without more data.

**Verdict sensitivity** — `alice_vs_bob`

| dimension | value | verdict |
|---|---|---|
| baseline | locked | switch |
| alpha | 0.01 | inconclusive_no_action ← flips |
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
| Cost provenance | does not survive | n/a |

## Cost-quality view

**Pareto frontier (max success_rate, min total_cost_usd):** ['alice', 'bob']

All agents are on the frontier; no dominance to report.

## Residual risks

**Inherited from scouting decision** (verbatim from `scouting/byo-minimal-decision.md`):

_(no scouting decision document at scouting/byo-minimal-decision.md; residual risks not surfaced.)_

## Reproducibility footer

- **rendered_at:** `2026-05-03T09:54:11.496762+00:00`
- **git_commit:** `49adc49`
- **fixture_sha256:** `687cf4d211662ca65fbbfbdcfdab5349cad2b33b99d02fd8d412645798038c41`
- **bootstrap_seed:** `42`
