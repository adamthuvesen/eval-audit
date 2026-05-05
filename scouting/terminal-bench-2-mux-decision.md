# Terminal-Bench 2.0 Mux scouting decision

**Decided:** 2026-05-04

This note scouts a public-submission audit:

> On Terminal-Bench 2.0, does the public Mux + GPT-5.3-Codex submission
> outperform the public Mux + Claude Opus 4.6 submission once the comparison is
> analyzed as paired task outcomes instead of two leaderboard point estimates?

## Decision

**Proceed as a success-rate public-submission audit, with cost suppressed.**

The public artifacts pass the task-level evidence gate:

- The official Terminal-Bench 2.0 leaderboard publishes both Mux rows.
- The Hugging Face leaderboard dataset publishes one `result.json` per
  task/trial under each submission.
- Both selected submissions use the same public agent family, Mux by Coder.
- Both selected submissions have five runs over the same 89 task names.
- Each `result.json` exposes a binary verifier reward through
  `verifier_result.rewards.reward`.

Do **not** present this as a clean model-only result. It is a comparison between
two public Mux submissions using different model providers and different
submission dates.

## Locked candidate

| Field | Value |
|---|---|
| Benchmark | `terminal-bench-2` |
| Task source | Terminal-Bench 2.0 public leaderboard dataset |
| Source task key | `task_name` |
| Treatment | `Mux__GPT-5.3-Codex` |
| Control | `Mux__Claude-Opus-4.6` |
| Treatment display | Mux + GPT-5.3-Codex |
| Control display | Mux + Claude Opus 4.6 |
| Outcome | `success_rate` |
| Public trials | 5 per agent |
| Task universe | 89 task names |
| Official treatment row | 74.6% ± 2.5 |
| Official control row | 66.5% ± 2.5 |

The official leaderboard rows are context only. The committed report must be
regenerated from the public `result.json` artifacts through the local
`eval-audit` pipeline.

## Source artifacts checked

- Official leaderboard:
  `https://www.tbench.ai/leaderboard/terminal-bench/2.0`
- Public leaderboard dataset:
  `https://huggingface.co/datasets/harborframework/terminal-bench-2-leaderboard`
- Treatment metadata:
  `submissions/terminal-bench/2.0/Mux__GPT-5.3-Codex/metadata.yaml`
- Control metadata:
  `submissions/terminal-bench/2.0/Mux__Claude-Opus-4.6/metadata.yaml`

## Outcome mapping

For the adapter:

- `task_id`: Terminal-Bench `task_name`.
- `agent_id`: Hugging Face submission directory name.
- `run_id`: public job timestamp directory.
- `success=True`: `verifier_result.rewards.reward >= 1.0`.
- `success=False`: `verifier_result.rewards.reward < 1.0`.
- `outcome_status="errored"`: reserved for missing verifier rewards.
- token fields: copied from `agent_result.n_input_tokens` and
  `agent_result.n_output_tokens`.
- cost fields: null, with `cost_provenance="cost_not_available"`.

## Residual risks

1. **Not a clean model-only effect.** The comparison is between public Mux
   submissions, not two models inside a controlled local experiment. The two
   rows differ by model provider and submission date, and may inherit runtime
   or environment differences not visible in the row-level JSON.

2. **Cost is incomplete, not zero.** Public `result.json` rows expose token
   counts, but `agent_result.cost_usd` is missing or zero-placeholder for many
   treatment rows and only partially populated for the control. The report must
   suppress cost-derived columns, Pareto frontier, and `hedge_on_cost`
   decisions.

3. **Leaderboard confidence intervals are not reused as inference.** The
   official 74.6% and 66.5% rows are useful public context, but the report's
   inference comes from the committed task-level rows and paired analysis.

4. **Five trials per task are public artifacts, not a rerun plan.** The audit
   treats the observed five trials per submission as fixed evidence. It does
   not claim the user can reproduce those exact trials locally.

5. **Terminal execution tasks can have environment-sensitive failures.** The
   public task outcomes are accepted as published, but any deeper causal claim
   about why a task failed would require the full execution traces.

## Reproducibility command

```bash
uv run python tools/regenerate_terminal_bench_mux.py
```

That command fetches the public Hugging Face leaderboard artifacts, writes the
canonical `examples/terminal-bench-2-mux/runs.parquet`, and records source
manifest hashes in `examples/terminal-bench-2-mux/provenance.json`.
