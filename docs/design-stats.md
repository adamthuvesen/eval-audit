# Stats design rules

Intervals, bootstrap, multiple-comparison correction, paired analysis, and the
Pareto frontier live in [eval_audit/stats](../eval_audit/stats).

- Task is the unit of paired analysis. Avoid naive row-level shortcuts that
  ignore task clustering.
- Errored rows count as failures in headline denominators while still surfacing
  `n_errored`.
- Keep bootstrap seeds and iteration counts explicit where reproducibility
  matters.
- Multiple-comparison correction is part of the declared claim family. Do not
  report unadjusted significance as the decision.
- Prefer clear, boring statistical code over clever abstractions.

## Analysis settings and pairing

`AnalysisResult.settings` records alpha, bootstrap iterations, and bootstrap seed.
Reports and sensitivity scenarios use these settings from the result.
Explicit report overrides must match them.

Bootstrap intervals and paired t-tests use the same sorted task means.
Both reject mismatched task sets instead of silently intersecting them.
Repeated rows contribute to their task mean before task-level inference.

## Sensitivity scenarios

`stats/sensitivity.py` recomputes each scenario across all declared agents and claims.
Alpha scenarios update both bootstrap intervals and per-agent Wilson intervals.
Error exclusion can change other claims through the correction family or Pareto frontier.
A claim without errored rows can therefore change its verdict.

Error exclusion changes quality denominators and uses tasks with graded rows in both arms.
It preserves baseline costs under the declared accounting policy for claim comparisons and the Pareto frontier.
Fewer than two paired graded tasks makes the claim unavailable.
An agent without graded rows makes the Pareto assessment unavailable.
Reports show these cases as `not assessed`, with no scenario verdict.

Unavailable claims stay in the original correction family.
The correction uses p=1 for bookkeeping only.
Reports never expose this placeholder as an observed p-value or verdict.

`target_mde` is a precision diagnostic.
Meeting it does not guarantee a switch or prevent new evidence from changing a verdict.

## Calibration gate

`tests/synthetic_validation/test_calibration.py` uses a fixed seed across 128 independent simulation draws.
Each draw has 120 tasks, three replicates, and two Holm-corrected claims.
Shared task difficulty induces dependence between arms and replicates.
The null includes independent task-arm error masks with probability 0.10.
The alternative has a known treatment-control effect of 0.30 and no errors.

Acceptance bounds precede execution and use binomial quantiles with tail probability 0.001.
Null family rejection uses nominal alpha 0.05 as its upper reference rate.
Interval coverage uses nominal coverage 0.95 as its lower reference rate.
Large-effect detection uses a declared minimum reference rate of 0.90.
That detection reference is a smoke-test requirement, not a power guarantee.
The gate checks baseline inference and error-exclusion inference.
These finite cases do not establish calibration for every benchmark distribution.
