"""Controlled vocabulary copy for rendered audit reports."""

from __future__ import annotations

STATUS_VOCAB = {"supported", "unsupported", "inconclusive"}

# Each rationale follows the same template: which rule fired, what the rule
# means for the audit, and the action the verdict implies for a model selector.
# Per-claim numbers (delta, CI bounds, cost ratio) live in the **Why** bullet,
# not here.
VERDICT_RATIONALE: dict[str, str] = {
    "switch": (
        "Treatment beat control significantly (the adjusted p-value rejects the null at "
        "the declared α) and in the direction the claim predicts. The data supports the "
        "claim. Action: switch the default selection to the treatment, subject to cost "
        "acceptance."
    ),
    "hold": (
        "Treatment differs from control significantly, but in the OPPOSITE direction of "
        "the claim. The data falsifies the claim's stated direction rather than confirming "
        "it. Action: hold the current selection; this evidence does not warrant a switch."
    ),
    "drop_from_shortlist": (
        "Treatment is Pareto-dominated on the cost-quality frontier — another agent "
        "achieves equal-or-better quality at equal-or-lower cost. No quality argument can "
        "rescue a dominated point. Action: drop the treatment from the shortlist before "
        "deciding among the rest."
    ),
    "rerun_more_n": (
        "The bootstrap CI for the delta crosses zero (no decisive direction), and the cost "
        "gap is below the material threshold of 10% of the cheaper arm. Neither side has a "
        "clean argument from this evidence. Action: collect more paired tasks before "
        "deciding; the current N is under-resolved for the question asked."
    ),
    "hedge_on_cost": (
        "The bootstrap CI for the delta crosses zero (no quality decision is available), "
        "but the cost gap is material (≥10% of the cheaper arm's cost). The decision "
        "pivots on cost preference rather than measured quality. Action: pick the cheaper "
        "arm unless the (statistically indistinguishable) quality difference matters to "
        "your use case."
    ),
    "inconclusive_no_action": (
        "The bootstrap CI for the delta is one-sided (does not cross zero), but the "
        "correction-adjusted p-value does not reject at α — the audit's declared "
        "inference contract requires a significant correction-adjusted test before "
        "claiming direction. No dominance or cost-gap rule fires. Action: keep the "
        "current selection until additional evidence (more N to tighten the test, or "
        "cost data that triggers the cost-gap rule) shifts the picture."
    ),
}
