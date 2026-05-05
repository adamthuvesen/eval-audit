# Exhibit C — Reproduction Recipe

This directory contains the predeclared design and the harness for the
controlled-evidence audit known as Exhibit C. See
[`../exhibit-c-decision.md`](../exhibit-c-decision.md) for the locked
decision and [`./run-plan.md`](./run-plan.md) for the pre-outcome run plan.

## Layout

```text
scouting/exhibit-c/
├── README.md                 (this file)
├── NOTICE                    (HumanEval MIT attribution)
├── run-plan.md               (predeclared run plan — task IDs, harness, settings)
├── price-table.yaml          (per-model rates dated 2026-05-03)
├── humaneval-tasks-30.jsonl  (vendored 30-task subset; sampled with seed=42)
├── run.py                    (calls Anthropic Messages API; writes raw/)
├── grade.py                  (subprocess execution of HumanEval tests; writes graded/)
├── normalize.py              (graded/ → examples/exhibit-c/runs.parquet)
├── raw/                      (gitignored; per-call API responses)
└── graded/                   (gitignored; per-call graded outputs)
```

## Reproducing from scratch

Pre-requisite: `ANTHROPIC_API_KEY` in `.env.local` at the repo root (the
harness does not call any other provider). Estimated cost: <\$2.

```bash
# 1. Predeclaration is committed; tasks are vendored. No model has been called yet.
uv run eval-audit spec validate studies/exhibit-c.yaml

# 2. Run the controlled evidence collection.
uv run python scouting/exhibit-c/run.py     # 120 API calls, ~5–10 minutes

# 3. Grade the raw outputs in subprocess (no eval in parent).
uv run python scouting/exhibit-c/grade.py

# 4. Normalize into the canonical RunRecord parquet.
uv run python scouting/exhibit-c/normalize.py

# 5. Validate the canonical parquet.
uv run eval-audit validate examples/exhibit-c/runs.parquet studies/exhibit-c.yaml

# 6. Analyze + render.
uv run eval-audit analyze studies/exhibit-c.yaml --runs examples/exhibit-c/runs.parquet \
  --bootstrap-iterations 8000 --bootstrap-seed 42
uv run eval-audit report  studies/exhibit-c.yaml --runs examples/exhibit-c/runs.parquet \
  --bootstrap-iterations 8000 --bootstrap-seed 42
```

## What is and is not committed

Committed:

- `humaneval-tasks-30.jsonl` (vendored evidence subset).
- `run.py`, `grade.py`, `normalize.py` (deterministic transforms).
- `examples/exhibit-c/runs.parquet` (canonical RunRecord fixture).
- `reports/exhibit-c/{analysis.json,report.md}` (rendered audit artifacts).

Gitignored:

- `scouting/exhibit-c/raw/` and `scouting/exhibit-c/graded/` (verbose per-call
  payloads — regeneratable from the API + the deterministic grader).

## Provider non-determinism

The Anthropic Messages API at `temperature=0` is approximately but not
strictly deterministic. The 2 reruns per (agent, task) are intentional; they
capture provider-level run-to-run variance. If you re-run `run.py` on a
different day, `examples/exhibit-c/runs.parquet` may shift slightly and the
snapshot test will diff. That is the expected behavior of a controlled
*original* run — the report's Reproducibility section documents that the
parquet is the canonical artifact, not the raw API responses.
