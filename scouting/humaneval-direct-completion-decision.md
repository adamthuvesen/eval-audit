# HumanEval Direct Completion Decision

**Decided:** 2026-05-03

> Once written, this document is the contract the controlled-evidence audit consumes. Locked fields (task source, harness, model arms, cost classification, claim) MUST NOT be edited in place without an explicit follow-up note explaining the trigger.

---

## Corrigenda (2026-05-03, pre-decision)

### 1. Sonnet model_id typo (pre-outcome)

The original predeclaration named the Sonnet 4.6 model with a date-suffixed
id that does not exist on the Anthropic Messages API (HTTP 404
`not_found_error`). The canonical API id for Sonnet 4.6 is
`claude-sonnet-4-6` with no date suffix; the Haiku 4.5 id
`claude-haiku-4-5-20251001` is correct and unchanged.

This is a typo correction to the API endpoint string, not a redesign:

- Intent ("Claude Sonnet 4.6 via the Anthropic Messages API at temperature=0,
  max_tokens=1024") is unchanged.
- No Sonnet outcomes had been graded when the typo was caught. Every Sonnet
  call returned an HTTP 404 error, producing no completions and no token usage
  attributable to the model under test.
- Haiku 4.5 outcomes had been collected (60 raw API responses) but not yet
  graded; their design is unaffected by this correction.

Corrected fields below: model arm `treatment.model_id`, harness arms table,
and the candidate-claim text. The 30 task IDs, harness, settings, reruns,
grader, cost policy, errored-row policy, inference, stopping rule, and
treatment/control roles are all unchanged.

### 2. Grader indentation normalization (pre-decision, post-collection)

The original `grade.py` concatenated `prompt + completion` directly. Models
respond to "output only the function body" in three observed shapes:

1. body with the first line at column 0 and following lines at column 4,
2. fully unindented body that has its own 4-space nested indent
   (e.g. unindented `for ...:` over indented loop body),
3. a complete `def <fn>(...):` redefinition (sometimes plus a top-level
   `return` outside that helper).

Direct concatenation against the HumanEval prompt (which ends after the
docstring and expects an indented body) produced
`SyntaxError: 'return' outside function` for shape (2),
`IndentationError: expected an indented block` for naive 4-space indent on
shape (2), and inconsistent behavior for (1) and (3). This affected both
arms but disproportionately Sonnet, which preferred shapes (2) and (3)
more often than Haiku.

`grade.py::_build_program` now generates up to three candidate wrappings
and selects the first one that parses with `ast.parse`:

- A. shape-(3) wrapping: prompt content before the first `def` + the
  model's full function + tests.
- B. shape-(1) wrapping: indent only lines that aren't already indented.
  Preserves "first line at col 0, rest at col 4" structure.
- C. shape-(2) wrapping: indent every non-empty line by 4 spaces.
  Preserves the model's own nested indentation when the whole body sits
  at module level.

If none parse, the first candidate is run anyway and the resulting
`SyntaxError` surfaces in `stderr_tail`. This is intentional: a completion
that nothing makes parseable is genuinely ungradeable, and the honest
outcome is `success=False`.

- The raw API responses under `scouting/humaneval-direct-completion/raw/` are the source of
  truth and are unchanged. Only the grader's interpretation changed.
- No analysis ran against any buggy grade. `eval-audit analyze` and
  `eval-audit report` had not yet been invoked when the bug was identified.
- The harness id `eval-audit/humaneval-direct-completion-v1` is unchanged. The
  multi-strategy normalization is part of v1's defined grader behavior;
  future harness versions may compare against it.

---

## Decision

**HumanEval Direct Completion: HumanEval (Anthropic Messages API, base-LLM direct-completion harness)**

Selected as the smallest credible controlled-evidence audit:

- HumanEval has fully public prompts + ground-truth tests under MIT, so no contamination-of-process risk for distribution.
- A base-LLM-no-tools harness is meaningful for HumanEval (whereas it would be near-uninformative on agent benchmarks like GAIA).
- Execution-based grading is deterministic and local, with no LLM-as-judge variance to absorb into the audit.
- 30 tasks × 2 arms × 2 reruns = 120 API calls. Estimated cost is <\$2, and the run should finish in <10 minutes.

GAIA was the first instinct but rejected: GAIA tasks require a tool-using agent harness (web browsing, file IO, multi-step reasoning); a thin direct-API call would produce near-zero scores for both arms and a degenerate comparison. Building a real GAIA agent would expand this change well beyond a single controlled audit.

---

## Locked fields (contract for `add-controlled-real-evidence-exhibit`)

### Task source

| field | value |
|---|---|
| benchmark | `humaneval` |
| source | `openai/human-eval` (MIT) |
| sampling | `random.Random(42).sample(range(164), 30)` over `HumanEval/0` through `HumanEval/163`, sorted ascending |
| n_tasks | 30 |
| committed task IDs | see `scouting/humaneval-direct-completion/run-plan.md` |

### Harness

| field | value |
|---|---|
| harness id | `eval-audit/humaneval-direct-completion-v1` |
| version pin | git commit hash of `scouting/humaneval-direct-completion/run.py` at run time, captured in `rerun_metadata` |
| tools | none |
| system prompt | "Complete the following Python function. Output only the function body. No triple backticks, no `def` line, no surrounding prose." |
| user prompt | the HumanEval `prompt` field verbatim |
| temperature | `0` |
| max_tokens | `1024` |

### Model arms

| arm role | agent_id | model_id | settings |
|---|---|---|---|
| treatment | `humaneval-direct-sonnet-4-6` | `claude-sonnet-4-6` | temperature=0, max_tokens=1024 |
| control | `humaneval-direct-haiku-4-5` | `claude-haiku-4-5-20251001` | temperature=0, max_tokens=1024 |

Both arms hit the Anthropic Messages API. Both arms run on the same 30 task IDs.

### Reruns

| field | value |
|---|---|
| runs per (agent, task) | 2 |
| run_id format | `run-{agent_short}-{1\|2}` |
| seed | none (Anthropic API does not honor a seed parameter as of price-table date); temperature=0 is the only determinism lever available |
| rerun policy | `capture_provider_nondeterminism`; both runs preserved; analysis aggregates per task per the existing engine |

### Grader

Local Python subprocess. For each task:

1. Concatenate the HumanEval `prompt` + the model's completion.
2. Append the HumanEval `test` field and a `check(<entry_point>)` invocation.
3. Run under `python` with `subprocess.run(timeout=10)`.
4. Exit code `0` → `success=True`; non-zero → `success=False`. Timeout / crash → `success=False`.
5. API errors / parse failures → `outcome_status="errored"`, `success=null`, contributes to denominator per the existing errored-row policy.

No `eval()` of model output in the parent process. Each grade runs in its own temp dir under `/tmp/humaneval-direct-completion-grade-<uuid>/`.

### Cost classification

`reconciled` when reconstructed per-task cost (from `tokens_in_by_model` × prices in `scouting/humaneval-direct-completion/price-table.yaml`) matches the Anthropic Messages API's recorded `usage` field within 0.5¢. Otherwise `as_reported_only`. The reconstructed-vs-reported reconciliation is computed per-row at normalization time.

Price-table date: **2026-05-03**.

| model | input ($/MTok) | output ($/MTok) |
|---|---|---|
| claude-haiku-4-5-20251001 | 0.80 | 4.00 |
| claude-sonnet-4-6 | 3.00 | 15.00 |

### Errored-row policy

API error / parse failure / timeout / non-zero unrelated exception → `outcome_status="errored"`, `success=null`, counts in the headline denominator as a failure (mirrors the v0 contract).

### Inference

| field | value |
|---|---|
| α | 0.05 |
| correction | Holm-Bonferroni |
| comparison family | declared_claims |
| target MDE | 0.10 (small N) |
| bootstrap iterations | 8000 |
| bootstrap seed | 42 |

### Stopping rule

Fixed 30-task list. No peeking at outcomes and extending. If decision-sensitive ambiguity remains after the 120 API calls, a follow-up exhibit (HumanEval Direct Completion-2) handles it; the original is not retroactively grown.

### Candidate claim

> On a 30-task HumanEval slice (seed=42) under a thin direct-completion harness with tools disabled and temperature=0, Claude Sonnet 4.6 and Claude Haiku 4.5 are compared on `success_rate`. The audit asks whether any observed gap is statistically distinguishable from noise on n=30 (target MDE 0.10), and what the cost-quality tradeoff looks like.

- **treatment:** `humaneval-direct-sonnet-4-6`
- **control:** `humaneval-direct-haiku-4-5`
- **outcome:** `success_rate`
- **n_per_arm:** 30 task IDs × 2 reruns each → 60 rows per arm in the canonical parquet; analysis aggregates per task per the existing engine

This claim is **predeclared** before any outcome is observed, in contrast with GAIA HAL Generalist and TAU-bench Airline Tool Calling which reanalyze published runs.

---

## Residual risks

1. **HumanEval is in training data.** Both Haiku 4.5 and Sonnet 4.6 have almost certainly seen HumanEval during pretraining. The audit demonstrates audit methodology, not frontier-capability claims. The report's Residual Risks section calls this out.

2. **Provider non-determinism at temperature=0.** The Anthropic Messages API at temperature=0 is roughly deterministic, but not strictly. The 2 reruns capture provider-level run-to-run variance and contribute to the bootstrap CIs. If reruns within an arm disagree on a task, both rows are kept; the existing analysis engine aggregates per task.

3. **No tools, no scaffold.** HumanEval Direct Completion uses a thin harness: a single API call per task, no tool use, no agent framework. This gives a clean audit, but it does not represent how either model would perform under a richer scaffold. The exhibit is explicitly "controlled original evidence under harness `eval-audit/humaneval-direct-completion-v1`", not a frontier-capability comparison.

4. **Small N.** n=30 tasks gives a target MDE of ~0.10. Effects smaller than 10 percentage points may be detectable only as wide CIs; the report surfaces this in Verdict Sensitivity.

5. **Within-harness only.** Like GAIA HAL Generalist and TAU-bench Airline Tool Calling, this audit compares two arms within ONE harness. Cross-harness comparisons are out of scope by repo policy.

---

## Order of operations (preregistration discipline)

The following order MUST be respected to honor the predeclared design:

1. Commit `scouting/humaneval-direct-completion-decision.md`, `scouting/humaneval-direct-completion/run-plan.md`, `studies/humaneval-direct-completion.yaml` (this file and its siblings). *No API calls have been made.*
2. Vendor the 30-task HumanEval subset to `scouting/humaneval-direct-completion/humaneval-tasks-30.jsonl` from `openai/human-eval`'s release JSONL. *Still no outcomes.*
3. Commit the harness scripts (`run.py`, `grade.py`, `normalize.py`).
4. Run `scouting/humaneval-direct-completion/run.py`. *First contact with outcomes.*
5. Grade, normalize, validate, analyze, render.

If any locked field above changes after step 4, the change is a new exhibit (HumanEval Direct Completion-2) with its own decision document, not an in-place edit.

---

## Immutability

The fields locked above (task source, harness, model arms, settings, reruns, grader, cost classification, errored-row policy, inference, stopping rule, claim) MUST NOT be edited in place once this document is committed. Changes require a follow-up note that explicitly references this decision and explains the trigger. This is a convention, not a CI check; rely on git history to enforce it.
