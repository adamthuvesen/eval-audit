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
