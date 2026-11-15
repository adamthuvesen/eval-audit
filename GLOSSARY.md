# eval-audit

eval-audit decides whether benchmark score differences between agents are large, reliable, and cost-aware enough to justify a model switch.

## Language

**Study**:
The declared YAML plan for one audit: agents, claims, design, inference settings, and cost view (`StudySpec`).

**Run**:
One execution of one agent over the whole task set, named by `run_id` (`docs/INPUT_CONTRACT.md`).
_Elsewhere_: a counterfact `Run` is one trace of one task, a heist run is one invocation over agents x tasks, and skill-lab has cycles, not runs.

**RunRecord**:
The canonical task-level row: one agent's result on one task in one run. `docs/run-record.schema.json` is the contract that exporters copy.
_Avoid_: result row. heist calls its own task-level row `TaskRunResult`.

**Agent**:
The system under test: the model plus scaffold whose task outcomes the audit compares (`agent_id`).
_Elsewhere_: in skill-lab, the agent is the optimizer that edits `SKILL.md`.

**Harness**:
The scaffold that produced a row (`harness`). Claims across different harnesses are refused as non-causal.
_Elsewhere_: heist exports `"heist"` as its harness.

**Claim**:
One declared comparison of a treatment agent against a control agent on one outcome.

**Arm**:
The treatment side or the control side of a claim.
_Elsewhere_: in counterfact, an arm is a chosen action of a decision.

**Verdict**:
The decision for one claim: `switch`, `hold`, `drop_from_shortlist`, `rerun_more_n`, `hedge_on_cost`, or `inconclusive_no_action` (`schema/enums.py::Verdict`).
The same values are also called "decision impact": `decision_impact()` returns a `Verdict`, and `DECISION_IMPACT_VOCAB` lists them. Reports print both names, so the drift is public, not internal.
_Elsewhere_: in skill-lab, a verdict is one judge's PASS, FAIL, or error for one input.

**Cost provenance**:
How far the cost data can be trusted: `reconciled`, `partial`, `as_reported_only`, or `cost_not_available` (`docs/design-ingest.md`).

**Sensitivity scenario**:
A re-analysis of the whole study with one setting changed (alpha 0.01 or 0.10, errored rows excluded, or no multiple-comparison correction) that shows whether a verdict holds (`stats/sensitivity.py`).
_Elsewhere_: a counterfact scenario is a synthetic causal model in its benchmark suite.

**Pareto frontier**:
The agents that no other agent dominates. Another agent dominates when it has at least the same success rate at no more cost, and is strictly better on one (`stats/pareto.py`).
_Elsewhere_: heist's `frontier` is a held-out task tier.
