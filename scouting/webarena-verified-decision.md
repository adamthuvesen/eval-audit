# WebArena Verified scouting decision

**Decided:** 2026-05-04

This note scouts a potential public-audience audit:

> On WebArena Verified (812 tasks full / 258 tasks hard), do two
> same-harness BrowserGym agents produce a paired success-rate decision
> when analyzed task by task rather than as two leaderboard point
> estimates?

The benchmark itself is the strongest fit we have evaluated so far for the
existing public-submission shape (SWE-bench Verified OpenHands, Terminal-Bench
2-mux): deterministic evaluators, single canonical task universe, audited
templates, structured JSON outputs. The blocker is evidence — public
**per-task** outcomes for two same-harness agents do not exist as of today.

## Decision

**No-go for now. Watch list.** A WebArena Verified `eval-audit` report is not
implementable today because no public source exposes per-task agent outcomes
under the Verified evaluator. The benchmark infrastructure exists and is
healthy; the leaderboard backend is provisioned but empty. Re-scout in
4–8 weeks against the watch items below.

This decision is consistent with the project rule: cautious refusal is better
than a polished but unsupported benchmark conclusion. The eval-audit v0
contract requires task-level paired comparisons within one harness; aggregate
score + std_err rows cannot satisfy that contract no matter how attractive the
underlying benchmark is.

## What "go" would have required

Per-task evidence for ≥2 same-harness agents:

- one row per `(agent, task_id)` keyed by the canonical WebArena task name,
- a deterministic Verified-scoring success boolean (Verified rescores tasks
  under different evaluators than original WebArena, so original-WebArena
  logs are not substitutable),
- harness identity (BrowserGym version, scaffold variant such as
  `GenericAgent` or `Operator`),
- enough provenance to regenerate the fixture from a public source,
- ideally same scaffold across model swaps (e.g. two GenericAgent variants),
  not cross-scaffold (GenericAgent vs Operator), which would be a separate
  cross-harness audit and would hit the existing
  `CrossHarnessComparisonError` refusal.

Cost would have been declared `cost_not_available` regardless — the web-agent
tooling does not consistently publish per-task tokens or reconciled run
totals in a stable shape, and fabricating zeros is explicitly prohibited.

## Source artifacts checked (2026-05-04)

### ServiceNow/webarena-verified — partial

The repo at tag `v1.2.3` (2026-02-07) is a **runner**, not a results store.

- Top-level layout: `src/`, `examples/`, `dev/`, `tests/`, `docs/`. No
  `results/`, `runs/`, or `logs/` directory.
- `examples/agent_logs/demo/` contains fixtures for tasks `107` and `108`
  only — demo material, not a population of runs.
- 8 releases, none with attached run-log archives.
- `src/webarena_verified/types/eval.py` defines a clean per-task `result`
  contract (`result.score`, `result.status`) — the schema for honest per-task
  records exists; nobody has published populated logs to it.

### ServiceNow/BrowserGym — partial

- PR [#377](https://github.com/ServiceNow/BrowserGym/pull/377) (merged
  2026-01-20) ships `browsergym/webarena_verified/` and `webarena_verified.csv`
  with all 813 task definitions (`task_name`, `task_id`, `sites`,
  `eval_types=AgentResponseEvaluator`, `browsergym_split`).
- The `ServiceNow/browsergym-leaderboard` HF Space has agent dirs for
  `GenericAgent-Claude-3.5-Sonnet`, `…-3.7-Sonnet`, `…-4-Sonnet`,
  `GPT-4.1-Mini`, `GPT-5-mini`, `GPT-5-nano`, `AgentTrek-1.0-32b`,
  `A3-Qwen3.5-9B`, etc.
- Each agent dir contains only `webarena.json` (original WebArena, aggregate);
  **no `webarena_verified.json` exists in any agent dir**.
- Confirmed shape of `webarena.json`: a single aggregate row keyed by
  `agent_name` with `study_id` (UUID), `score`, `std_err` — no per-task
  array. The leaderboard schema discards per-task rows by construction.

### ServiceNow/AgentLab — partial

- `reproducibility_journal.csv` records same-harness original-WebArena
  GenericAgent runs (gpt-4o-mini 0.174, gpt-4o 0.314, claude-3.5-sonnet 0.362,
  o1-mini 0.286, llama-3.1-70b 0.184, llama-3.1-405b 0.240; all 812/812 on
  benchmark `webarena 0.13.3`).
- **Zero rows for `webarena_verified`** as of 2026-05-04.
- The AgentLab `Study` class auto-uploads aggregate rows to the journal but
  does **not** push the per-task `study_*` artifact directories to a public
  bucket. The 207 GB `agentlabtraces/agentlabtraces` HF dataset only contains
  the TMLR-paper trace splits (`tmlr_traces_part_a[a-e]`); no WebArena split
  is surfaced.

### OpenReview supplementary — miss

- Two forums: `94tlGxmqkN` (workshop) and `CSIo4D7xBG` (ICLR 2026,
  **withdrawn**).
- The abstract promises "Code, data, and evaluation tools will be released."
  No per-task supplementary archive is attached to either forum page.
- The ICLR 2026 withdrawal is itself a signal that any reproducibility
  package release is on a slower cadence than the public release of the
  runner.

### Hugging Face Hub — miss (with one notable empty placeholder)

- [`AmineHA/Webarena-Verified-Submissions`](https://huggingface.co/datasets/AmineHA/Webarena-Verified-Submissions):
  created 2026-02-07 by the WebArena Verified lead author. **Empty** as of
  2026-05-04 (`.gitattributes` + 31-byte placeholder README, "The dataset is
  currently empty"). This is the canonical drop point for the leaderboard
  backend named by the maintainers and is the highest-signal item on the
  watch list.
- [`AmineHA/WebArena-Verified`](https://huggingface.co/datasets/AmineHA/WebArena-Verified):
  task definitions only (full 812, hard 258).
- `OpenHandsCommunity/eval-output-webarena`: original WebArena, single agent
  (`BrowsingAgent`) — useful for OpenHands-on-WebArena work but not Verified
  and not paired.
- `webarena-x/webarena-infinity-trajectories`: training trajectories, not
  evaluation results.

### Author repos — miss

- Authors: Amine El hattami (`Am1n3e` / `AmineHA`), Megh Thakkar, Nicolas
  Chapados, Christopher Pal.
- `Am1n3e` is the active maintainer of `webarena-verified` and owner of the
  empty submissions dataset. No personal reproducibility releases on author
  repos beyond the official ServiceNow channels.

## Outcome mapping (would-be, when go)

For a future adapter, mirror `eval_audit/ingest/swe_bench_verified.py`:

- `task_id`: canonical WebArena task config name (the `task_name` column in
  `webarena_verified.csv`).
- `success=True`: `result.status == "pass"` under the Verified evaluator
  (substring → type-aware exact match — distinct from the original
  WebArena evaluator).
- `success=False`: any non-pass Verified status with a graded run.
- `outcome_status="errored"`: ungraded harness error (no Verified evaluator
  output produced).
- `cost_provenance="cost_not_available"`; both cost columns null; tokens
  encoded with the `{"upstream_tokens_unavailable": 0}` sentinel mirror
  the SWE-bench Verified adapter.
- Harness identity must include the BrowserGym version and scaffold name
  (e.g. `browsergym==0.13.3 + GenericAgent`) — Verified-vs-original is a
  benchmark difference, not a harness difference.

## Residual risks / gaps blocking us

1. **No populated public source.** Six independent targets returned no
   per-task Verified outcomes. The closest is an explicitly empty
   submissions dataset.
2. **Verified ≠ original WebArena.** Existing AgentLab journal rows for
   `webarena 0.13.3` cannot be rescored as Verified without rerunning the
   evaluator against per-task agent outputs we do not have.
3. **Single-scaffold pair not yet possible.** Even when submissions land,
   the first uploads are likely heterogeneous. A clean same-scaffold pair
   (e.g. `GenericAgent + Claude 4 Sonnet` vs `GenericAgent + GPT-5`) is the
   minimum for an `eval-audit` paired comparison.
4. **Aggregate-only leaderboard schema.** Even if per-task logs are produced
   downstream, the `browsergym-leaderboard` schema discards them. Any future
   audit must source from the submissions dataset (or equivalent), not the
   leaderboard JSON.
5. **ICLR 2026 withdrawal slows reproducibility cadence.** The supplementary
   release schedule is uncertain.
6. **Cost remains structurally unavailable.** Web-agent runs do not
   consistently publish reconciled cost. Plan on
   `cost_not_available` and Pareto suppression from day one.

## Watch list — re-scout in 4–8 weeks

1. **`huggingface.co/datasets/AmineHA/Webarena-Verified-Submissions`** —
   first uploads here are the canonical signal. Re-check populated state
   and per-row schema (look for a `task_name` / `result.status` shape).
2. **`ServiceNow/webarena-verified-leaderboard`** — leaderboard repo with
   active intake-validation work (issues #27 "Feature/add leaderboard",
   #33–35 building lanes D/E/F). When this ships, submissions are expected
   to carry per-task evaluator output by design.
3. **AgentLab `reproducibility_journal.csv`** — first appearance of any
   `benchmark=webarena_verified` row (full or hard). The 258-task hard
   subset is the natural first target (lower compute) and is where models
   still differentiate.
4. **OpenReview forum `94tlGxmqkN` and the next paper venue** — supplementary
   archive attachments.

## Reproducibility commands (negative results)

```bash
# 1. Confirm submissions dataset is empty.
curl -sL https://huggingface.co/api/datasets/AmineHA/Webarena-Verified-Submissions/tree/main \
  | jq '.'
# Expected: only .gitattributes and a small README.

# 2. Confirm browsergym-leaderboard agent dirs lack webarena_verified.json.
curl -sL https://huggingface.co/api/spaces/ServiceNow/browsergym-leaderboard/tree/main/results \
  | jq -r '.[].path'
# For each agent dir: only webarena.json (original) is present.

# 3. Confirm AgentLab journal has zero webarena_verified rows.
curl -sL https://raw.githubusercontent.com/ServiceNow/AgentLab/main/reproducibility_journal.csv \
  | awk -F, '$2 ~ /webarena_verified/'
# Expected: no output.

# 4. Confirm webarena-verified runner has no committed run logs.
gh api repos/ServiceNow/webarena-verified/contents/ --jq '.[].name'
gh api repos/ServiceNow/webarena-verified/releases --jq '.[].assets[].name'
# Expected: no results/, runs/, or logs/ directories; no run-log archive
# attached to any release.
```

## Recommendation

Do not implement an adapter, study, fixture, regen tool, or report for
WebArena Verified today. The next implementation step is **conditional**:
when the watch-list signals fire (most likely the submissions dataset
gaining its first populated rows), re-run this scouting pass. If two
same-scaffold agents become available with per-task Verified outcomes,
mirror `eval_audit/ingest/swe_bench_verified.py` and ship a
`cost_not_available` success-rate audit.

In the meantime, Terminal-Bench 2-mux and SWE-bench Verified OpenHands remain
the two shipped public-submission exhibits. WebArena (original, non-Verified)
is **not** a substitute: rescoring under the Verified evaluator requires
per-task outputs we do not have, and the AgentLab journal exposes only
aggregate rows for original WebArena.
