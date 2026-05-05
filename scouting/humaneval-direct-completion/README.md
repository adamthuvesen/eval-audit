# HumanEval Direct Completion — Reproduction Recipe

This directory contains the predeclared design and the harness for the
controlled-evidence audit known as HumanEval Direct Completion. See
[`../humaneval-direct-completion-decision.md`](../humaneval-direct-completion-decision.md) for the locked
decision and [`./run-plan.md`](./run-plan.md) for the pre-outcome run plan.

## Layout

```text
scouting/humaneval-direct-completion/
├── README.md                 (this file)
├── NOTICE                    (HumanEval MIT attribution)
├── run-plan.md               (predeclared run plan — task IDs, harness, settings)
├── price-table.yaml          (per-model rates dated 2026-05-03)
├── humaneval-tasks-30.jsonl  (vendored 30-task subset; sampled with seed=42)
├── run.py                    (calls Anthropic Messages API; writes raw/)
├── grade.py                  (subprocess execution of HumanEval tests; writes graded/)
├── normalize.py              (graded/ → examples/humaneval-direct-completion/runs.parquet)
├── raw/                      (gitignored; per-call API responses)
└── graded/                   (gitignored; per-call graded outputs)
```

## Reproducing from scratch

Pre-requisite: `ANTHROPIC_API_KEY` in `.env.local` at the repo root (the
harness does not call any other provider). Estimated cost: <\$2.

```bash
# 1. Predeclaration is committed; tasks are vendored. No model has been called yet.
uv run eval-audit spec validate studies/humaneval-direct-completion.yaml

# 2. Run the controlled evidence collection.
uv run python scouting/humaneval-direct-completion/run.py     # 120 API calls, ~5–10 minutes

# 3. Grade the raw outputs in subprocess (no eval in parent).
uv run python scouting/humaneval-direct-completion/grade.py

# 4. Normalize into the canonical RunRecord parquet.
uv run python scouting/humaneval-direct-completion/normalize.py

# 5. Validate the canonical parquet.
uv run eval-audit validate examples/humaneval-direct-completion/runs.parquet studies/humaneval-direct-completion.yaml

# 6. Analyze + render.
uv run eval-audit analyze studies/humaneval-direct-completion.yaml --runs examples/humaneval-direct-completion/runs.parquet \
  --bootstrap-iterations 8000 --bootstrap-seed 42
uv run eval-audit report  studies/humaneval-direct-completion.yaml --runs examples/humaneval-direct-completion/runs.parquet \
  --bootstrap-iterations 8000 --bootstrap-seed 42
```

## What is and is not committed

Committed:

- `humaneval-tasks-30.jsonl` (vendored evidence subset).
- `run.py`, `grade.py`, `normalize.py` (deterministic transforms).
- `examples/humaneval-direct-completion/runs.parquet` (canonical RunRecord fixture).
- `reports/humaneval-direct-completion/{analysis.json,report.md}` (rendered audit artifacts).

Gitignored:

- `scouting/humaneval-direct-completion/raw/` and `scouting/humaneval-direct-completion/graded/` (verbose per-call
  payloads — regeneratable from the API + the deterministic grader).

## Provider non-determinism

The Anthropic Messages API at `temperature=0` is approximately but not
strictly deterministic. The 2 reruns per (agent, task) are intentional; they
capture provider-level run-to-run variance. If you re-run `run.py` on a
different day, `examples/humaneval-direct-completion/runs.parquet` may shift slightly and the
snapshot test will diff. That is the expected behavior of a controlled
*original* run — the report's Reproducibility section documents that the
parquet is the canonical artifact, not the raw API responses.

## Grader trust boundary

The grader executes untrusted model-generated code. The v0 sandbox is:

- **Sanitized environment** — only `PATH` is forwarded; `ANTHROPIC_API_KEY`,
  `HOME`, and other parent-process variables are scrubbed.
- **Python isolated mode** (`-I`) — ignores `PYTHONPATH`, `PYTHONHOME`, and
  user site-packages, so the candidate cannot import repo-local code.
- **10-second timeout** per candidate.
- **Temporary working directory**.

Stronger isolation (container, network deny, rlimit-based memory cap) is
out of scope for v0. Do not run this grader on shared infrastructure or
with secrets present in the parent process's environment.
