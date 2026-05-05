# HumanEval Direct Completion — Pre-Outcome Run Plan

**Locked:** 2026-05-03 (before any model API call has been made for this audit)

**Corrigenda 2026-05-03 (pre-decision):**

- Sonnet 4.6 model_id corrected from a 404 date-suffixed alias to `claude-sonnet-4-6` before any Sonnet outcomes were graded.
- `grade.py` indentation normalization added before any analysis ran (raw API responses unchanged; grader interpretation only).

See [`../humaneval-direct-completion-decision.md`](../humaneval-direct-completion-decision.md#corrigenda-2026-05-03-pre-decision) for the full context.

This artifact is the predeclared run plan. It exists to make the controlled-evidence audit's design auditable: a reader can verify that the task IDs, harness, model arms, settings, cost policy, errored-row policy, and stopping rule were committed *before* any outcome was observed.

> Source-of-truth for the broader HumanEval Direct Completion contract: [`scouting/humaneval-direct-completion-decision.md`](../humaneval-direct-completion-decision.md). When this run-plan and the decision document conflict, the decision document wins.

---

## Study path (planned)

`studies/humaneval-direct-completion.yaml` — committed alongside this run-plan.

---

## Task source

| field | value |
|---|---|
| benchmark | `humaneval` |
| upstream source | <https://github.com/openai/human-eval> (MIT) |
| upstream artifact | `HumanEval.jsonl.gz` (164 tasks, validation set) |
| local vendored copy | `scouting/humaneval-direct-completion/humaneval-tasks-30.jsonl` (committed; sampled subset) |
| sampling method | `random.Random(42).sample(range(164), 30)`, sorted ascending by index |
| n_tasks | 30 |

### Locked task IDs

The 30 task IDs below are the *only* tasks that will be graded for HumanEval Direct Completion. The list is fixed; no task may be added or removed after this run-plan is committed.

```
HumanEval/1
HumanEval/6
HumanEval/7
HumanEval/8
HumanEval/22
HumanEval/23
HumanEval/26
HumanEval/28
HumanEval/35
HumanEval/40
HumanEval/50
HumanEval/55
HumanEval/56
HumanEval/57
HumanEval/59
HumanEval/62
HumanEval/70
HumanEval/71
HumanEval/87
HumanEval/107
HumanEval/108
HumanEval/114
HumanEval/129
HumanEval/139
HumanEval/143
HumanEval/151
HumanEval/152
HumanEval/155
HumanEval/161
HumanEval/163
```

To regenerate locally:

```bash
uv run python -c "
import random
print('\n'.join(sorted([f'HumanEval/{i}' for i in random.Random(42).sample(range(164), 30)], key=lambda s: int(s.split('/')[1]))))
"
```

---

## Harness

| field | value |
|---|---|
| harness id | `eval-audit/humaneval-direct-completion-v1` |
| version pin | git commit hash of `scouting/humaneval-direct-completion/run.py` at run time, written into `rerun_metadata.harness_commit` |
| transport | Anthropic Messages API |
| tools | none |
| system prompt | `Complete the following Python function. Output only the function body — no triple backticks, no \`def\` line, no surrounding prose.` |
| user prompt | the HumanEval `prompt` field verbatim |
| temperature | `0` |
| max_tokens | `1024` |

---

## Model arms

| arm role | agent_id | model_id | settings |
|---|---|---|---|
| treatment | `humaneval-direct-sonnet-4-6` | `claude-sonnet-4-6` | temperature=0, max_tokens=1024 |
| control | `humaneval-direct-haiku-4-5` | `claude-haiku-4-5-20251001` | temperature=0, max_tokens=1024 |

Both arms run on the same 30 task IDs above.

---

## Reruns

| field | value |
|---|---|
| runs per (agent, task) | 2 |
| total rows in canonical parquet | 30 × 2 × 2 = 120 |
| run_id | `run-{agent_short}-1` and `run-{agent_short}-2` (e.g. `run-sonnet46-1`) |
| seed | none — Anthropic Messages API does not honor `seed`; temperature=0 is the only determinism lever |
| rerun policy id | `capture_provider_nondeterminism` |

If the two reruns disagree on a task, both rows are preserved; the existing analysis engine aggregates per task.

---

## Cost policy

- Per-call `usage.input_tokens` and `usage.output_tokens` are recorded into `tokens_in_by_model` / `tokens_out_by_model` per row.
- Per-task cost is reconstructed from `tokens_in × input_rate + tokens_out × output_rate` using the rates in [`scouting/humaneval-direct-completion/price-table.yaml`](price-table.yaml) (price-table date 2026-05-03).
- `cost_provenance` is set to `reconciled` per row when the reconstructed cost matches the cumulative API-reported cost within 0.5¢; otherwise `as_reported_only`.
- `reported_run_total_cost_usd` is the sum across all rows in the same `run_id` × `agent_id` group.

---

## Errored-row policy

API error / parse failure / 429 retry-exhaustion / subprocess timeout / unrelated subprocess crash → `outcome_status="errored"`, `success=null`, `partial_credit=null`. Errored rows count as failures in headline denominators while `n_errored` is reported separately (mirrors the v0 contract).

---

## Stopping rule

Fixed 30-task list. No outcome inspection mid-run. No task added/removed after this run-plan is committed.

If a model arm's API errors out catastrophically (e.g., entire run fails), the partial run is preserved as evidence; we do not retry-after-the-fact to "clean up" outcomes. A clean retry replaces the original raw output for that arm and is recorded in `rerun_metadata.retry_reason`.

---

## Inference (predeclared)

| field | value |
|---|---|
| α | 0.05 |
| correction | Holm–Bonferroni |
| comparison family | declared_claims |
| target MDE | 0.10 |
| bootstrap iterations | 8000 |
| bootstrap seed | 42 |

---

## Order of operations

1. **NOW** — this run-plan, [`../humaneval-direct-completion-decision.md`](../humaneval-direct-completion-decision.md), and [`../../studies/humaneval-direct-completion.yaml`](../../studies/humaneval-direct-completion.yaml) are committed. No API calls have been made.
2. **Next** — vendor the 30-task subset to `scouting/humaneval-direct-completion/humaneval-tasks-30.jsonl` from upstream HumanEval.
3. **Next** — commit `scouting/humaneval-direct-completion/run.py`, `grade.py`, `normalize.py`.
4. **Then** — run `run.py`. *First outcome contact.*
5. **Then** — grade, normalize, validate, analyze, render.

---

## What this run plan does NOT do

- Does not declare reasoning or sensitivity analyses outside the single primary claim.
- Does not measure latency, lower-is-better metrics, or composite scores.
- Does not introduce a benchmark-runner abstraction. The harness is a one-off script.
- Does not compare across harnesses.
- Does not treat any synthetic example as evidence.
