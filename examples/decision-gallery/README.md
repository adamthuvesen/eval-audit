# Decision Pattern Gallery

This is a **synthetic** worked example. It is not benchmark evidence. It exists to demonstrate how each `decision_impact` verdict in `eval_audit/report/decisions.py:DECISION_IMPACT_VOCAB` renders end-to-end, so a reader can see what a verdict looks like in a real audit report rather than only in the rationale prose. The real-data audits — GAIA HAL Generalist and TAU-bench Airline Tool Calling — are what carry the project's credibility; this gallery is for *teaching the verdict language*.

## What it covers

The gallery renders three claims, each calibrated to fire one decision rule that the existing committed reports do not exercise:

- **`hold`** — `hold_treatment` (2/10 successes, $0.02/task) vs `hold_control` (9/10, $0.05/task). The treatment significantly underperforms control. The treatment is cheaper, so it is not Pareto-dominated; the engine reaches the *rejects-null + direction-mismatch* branch and emits `hold`. This demonstrates the tool falsifying a claim — a strong credibility signal that the engine isn't a confirmation machine.
- **`rerun_more_n`** — `rerun_treatment` (5/10, $0.030/task) vs `rerun_control` (5/10, $0.032/task). Tied per-arm success rates with offsetting per-task wins, so the bootstrap CI clearly straddles zero. The cost gap is ~6.67% — below the 10% material threshold — so the engine emits `rerun_more_n` rather than `hedge_on_cost`.
- **`inconclusive_no_action`** — `inconc_treatment` (8/10, $0.04/task) vs `inconc_control` (4/10, $0.06/task). Per-task differences are entirely +1 or 0 (no negatives), so the bootstrap percentile CI is entirely positive. The raw t-test p-value (~0.030) is small enough to suggest signal, but Holm-Bonferroni adjustment across the three-claim family pushes the adjusted p above α=0.05. This is the CI/p disagreement case the verdict was designed for; the rationale text describes it as a fallback verdict.

The verdicts already covered by other committed reports (`switch` via BYO minimal, `hedge_on_cost` via GAIA HAL Generalist and TAU-bench Airline Tool Calling, `drop_from_shortlist` via TAU-bench Airline Tool Calling claim 3) are not duplicated here.

## How to read it

- The gallery study spec is at [`studies/decision-gallery.yaml`](../../studies/decision-gallery.yaml).
- Run data construction is in [`make_runs.py`](make_runs.py) — each agent's success vector and per-task cost have a comment block naming the targeted verdict and the rule branch it triggers.
- The rendered audit is at [`reports/decision-gallery/report.md`](../../reports/decision-gallery/report.md).
- Each claim includes a copyable summary plus a verdict explainer naming the
  first matching decision-rule branch.
- Field-level `RunRecord` reference: [`docs/INPUT_CONTRACT.md`](../../docs/INPUT_CONTRACT.md).

## Regenerating

```bash
python examples/decision-gallery/make_runs.py
uv run eval-audit report studies/decision-gallery.yaml \
    --runs examples/decision-gallery/runs.parquet \
    --skip-validation
```

`make_runs.py` does more than write parquet: after writing, it runs the analysis pipeline against the gallery study and asserts that each claim's realised verdict matches the calibration target. If a future contributor edits success counts or costs in a way that flips one of the verdicts (for example, by perturbing the Pareto frontier), the script exits non-zero and names the affected claim. Drift is caught at fixture-regeneration time, before it can land in a committed report.

## Calibration findings

All three target verdicts (`hold`, `rerun_more_n`, `inconclusive_no_action`) are reachable on N=10 paired tasks under Holm-Bonferroni at α=0.05 in the three-claim family. `inconclusive_no_action` is the most fragile of the three because it requires a CI/p disagreement: per-task differences must be entirely on one side of zero (so the bootstrap CI doesn't cross zero) while the t-test p-value is large enough that Holm correction pushes adjusted p above α. The calibration above (4 of 10 tasks where treatment wins, 6 ties, 0 losses, raw p ≈ 0.030, adjusted p ≈ 0.060) is one such configuration; small perturbations to success counts or family size could flip the verdict to `switch` (if treatment wins more) or `hedge_on_cost`/`rerun_more_n` (if a single negative difference is introduced).
