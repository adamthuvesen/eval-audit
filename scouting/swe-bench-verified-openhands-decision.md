# SWE-bench Verified OpenHands scouting decision

**Decided:** 2026-05-03

This note scouts a potential public-audience audit:

> On SWE-bench Verified, does the public OpenHands + Claude Opus 4.5
> submission outperform the public OpenHands + GPT-5 submission once the
> comparison is analyzed as paired task outcomes rather than two leaderboard
> point estimates?

This should be framed as a comparison between two **public submissions**, not
as a clean model-only effect. The submitted agents differ in model, runtime
details, and iteration budget.

## Decision

**Proceed as a success-rate scouting candidate, with caveats.**

The public result artifacts pass the task-level evidence gate:

- The SWE-bench Verified task universe is public and has 500 rows keyed by
  `instance_id`.
- Both submissions publish `results/results.json` in
  `swe-bench/experiments`, with per-instance resolved sets plus
  `no_generation` / `no_logs` metadata.
- Both submissions publish S3-backed artifacts under
  `s3://swe-bench-submissions/verified/<submission>/`, including
  `all_preds.jsonl`, per-instance logs, and trajectories.
- The paired task analysis is materially different from just reading the
  headline rates: OpenHands + Opus 4.5 resolves 388/500 and OpenHands + GPT-5
  resolves 359/500, but the paired discordants are 45 Opus-only solves vs 16
  GPT-5-only solves.

Do **not** present this as a fully cost-aware `eval-audit` audit yet. The
sampled trajectories and reports did not expose stable token/cost fields, and
the current v0 schema does not have an honest `cost_not_available` provenance
mode. A full report needs either:

1. a reliable token/cost extraction path from the OpenHands artifacts, or
2. an explicit no-cost-provenance report path that disables Pareto/cost claims
   rather than smuggling in zeros.

## Locked candidate

| Field | Value |
|---|---|
| Benchmark | `swe_bench_verified` |
| Task source | `SWE-bench/SWE-bench_Verified` test split, 500 rows |
| Source task key | `instance_id` |
| Treatment | `20251127_openhands_claude-opus-4-5` |
| Control | `20250807_openhands_gpt5` |
| Treatment display | OpenHands + Claude Opus 4.5 |
| Control display | OpenHands + GPT-5 |
| Outcome | `success_rate` |
| Treatment successes | 388/500 = 77.6% |
| Control successes | 359/500 = 71.8% |
| Observed delta | +5.8 pp |
| Paired discordants | 45 treatment-only, 16 control-only |
| Quick paired bootstrap CI | [+2.8 pp, +8.8 pp], seed=42, 8000 iterations |
| Quick exact McNemar p | 0.000264 |

The quick statistics above are scouting calculations only. The final report
must be regenerated through the committed `eval-audit` pipeline.

## Source artifacts checked

### Treatment

`evaluation/verified/20251127_openhands_claude-opus-4-5/`

- `metadata.yaml` advertises S3 logs and trajectories:
  `s3://swe-bench-submissions/verified/20251127_openhands_claude-opus-4-5/{logs,trajs}`.
- `README.md` reports 388 resolved instances (77.6%).
- The model line is `anthropic/claude-opus-4-5-202511017`, reasoning effort
  `high`, 500 max iterations.
- The README cites OpenHands Software Agent SDK commit `8e296334` and
  OpenHands benchmarks commit `58ef980`.
- Checklist declares pass@1, no SWE-bench test knowledge, no hints, and
  browsing disabled.
- S3 inventory sampled on 2026-05-03:
  - `all_preds.jsonl`: 500 lines, 500 unique `instance_id`s.
  - `logs/`: 498 `report.json` files, 498 `patch.diff`, 498
    `test_output.txt`, 498 `eval.sh`.
  - `trajs/`: 489 trajectory JSON files.

### Control

`evaluation/verified/20250807_openhands_gpt5/`

- `metadata.yaml` advertises S3 logs and trajectories:
  `s3://swe-bench-submissions/verified/20250807_openhands_gpt5/{logs,trajs}`.
- `README.md` reports 359 resolved instances (71.8%).
- The model line is `openai/gpt-5-2025-08-07`, reasoning effort `high`, 100
  max iterations.
- The README cites OpenHands commit
  `34bf9c2579ca5a25e452583eed38c6c0e45cebd6`.
- Checklist declares pass@1, no SWE-bench test knowledge, no hints, and
  browsing disabled.
- S3 inventory sampled on 2026-05-03:
  - `all_preds.jsonl`: 499 lines, 499 unique `instance_id`s.
  - `logs/`: 498 `report.json` files, 499 `patch.diff`, 499
    `test_output.txt`, 499 `eval.sh`.
  - `trajs/`: 500 trajectory JSON files.

## Outcome mapping

For a candidate adapter:

- `task_id`: SWE-bench Verified `instance_id`.
- `success=True`: instance appears in the submission's `resolved` list.
- `success=False`: instance is in the 500-task universe and absent from
  `resolved`.
- `outcome_status="errored"` should be reserved only if the upstream artifact
  exposes an ungraded harness error that should be separated from a graded
  failure. The public `results.json` shape alone only gives `no_generation`
  and `no_logs`, so the first adapter should either map those to graded
  failures with a residual-risk caveat or inspect per-instance logs before
  promoting them to `errored`.

The two public `results.json` files contain no unknown `instance_id`s relative
to the 500-row Verified split.

## Residual risks

1. **Not a clean model-only effect.** The comparison is between public
   OpenHands submissions. The Opus submission used a different OpenHands path
   (Software Agent SDK + benchmark commit) and 500 max iterations; the GPT-5
   submission cites an OpenHands commit and 100 max iterations. A report must
   say "OpenHands + Opus 4.5 submission vs OpenHands + GPT-5 submission," not
   "Opus 4.5 beats GPT-5."

2. **Cost provenance is unresolved.** Sampled `report.json` files expose patch
   application and test status. Sampled trajectory JSON files expose messages
   and terminal content. A recursive key scan of sampled trajectories found no
   stable `token`, `usage`, or `cost` fields. Do not publish cost/Pareto
   claims from this candidate until this is solved.

3. **Artifact completeness differs.** Treatment has 500 `all_preds` rows but
   only 489 trajectory files and 498 report files. Control has 499 `all_preds`
   rows, 500 trajectory files, and 498 report files. The success-rate audit can
   rely on `results.json`, but any deeper provenance/cost extraction must
   explain missing artifacts.

4. **`no_generation` / `no_logs` semantics need a deliberate mapping.**
   Treatment has 2 `no_generation` and 0 `no_logs`; control has 1
   `no_generation` and 0 `no_logs` in `results.json`. Whether these are
   `graded` failures or `errored` rows should be locked before the report.

5. **SWE-bench submission policy changed after these runs.** The
   `swe-bench/experiments` README notes a 2025-11-18 policy change for
   Verified and Multilingual submissions. The candidate should cite the exact
   submission directories and not imply all historical submissions meet the
   latest acceptance policy.

## Reproducibility commands

The scouting checks used anonymous public artifacts:

```bash
uv run python - <<'PY'
import json, urllib.request, random, math
import polars as pl

tasks = pl.read_parquet(
    "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/main/data/test-00000-of-00001.parquet"
)["instance_id"].to_list()
base = "https://raw.githubusercontent.com/swe-bench/experiments/main/evaluation/verified"

def resolved(submission: str) -> set[str]:
    data = json.load(urllib.request.urlopen(f"{base}/{submission}/results/results.json"))
    return set(data["resolved"])

treatment = resolved("20251127_openhands_claude-opus-4-5")
control = resolved("20250807_openhands_gpt5")
diffs = [(task in treatment) - (task in control) for task in tasks]

rng = random.Random(42)
boots = []
for _ in range(8000):
    boots.append(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs))
boots.sort()

a_only = sum(d == 1 for d in diffs)
b_only = sum(d == -1 for d in diffs)
disc = a_only + b_only
k = min(a_only, b_only)
p = 2 * sum(math.comb(disc, i) * 0.5**disc for i in range(k + 1))

print(sum(diffs) / len(diffs), boots[200], boots[7799], a_only, b_only, p)
PY

aws s3 ls s3://swe-bench-submissions/verified/20250807_openhands_gpt5/ \
  --no-sign-request --recursive --summarize --human-readable
aws s3 ls s3://swe-bench-submissions/verified/20251127_openhands_claude-opus-4-5/ \
  --no-sign-request --recursive --summarize --human-readable
```

## Recommendation

The next implementation step should be a narrow SWE-bench Verified adapter and
fixture generator only if the report can honestly handle absent costs. If the
v0 report must remain cost-aware for every audit, pause here and add an
explicit `cost_not_available`/success-only report path first.
