# scouting/

Scouting workspace for GAIA HAL Generalist and TAU-bench Airline Tool Calling fixture selection.

Outputs in this tree are the durable, machine-readable handoff from scouting to reanalysis: column inventories, sampled fixtures, cost reconciliation, and provenance.

## Layout

```text
scouting/
  README.md                    # this file
  gaia-hal-generalist-decision.md        # the locked GAIA HAL Generalist choice (written last)
  candidates/
    tau-bench/
      columns.json             # raw column inventory
      sample.parquet           # 100–5000 row representative sample
      cost-reconciliation.json # reconciled | partial | as_reported_only | not_applicable
      provenance.json          # source URL, retrieval timestamp, sampling seed
    gaia/
      ... (same shape)
    browsecomp/
      ... (same shape)
  synthetic/
    spec.yaml                  # generative parameters
    generate.py                # one-off generator (deterministic)
    runs.parquet               # synthesised run-level rows
    truth.json                 # ground-truth quantities for stats validation
```

## Candidates

Three candidates are inventoried per the spec:

| Candidate     | Source family                                  | Why included                                                |
|---------------|------------------------------------------------|-------------------------------------------------------------|
| `tau-bench`   | HAL (Princeton)                                | Strong contender — agent-oriented, cost data plausibly available |
| `gaia`        | HAL (Princeton)                                | Different task shape from TAU-bench; tests gate calibration |
| `browsecomp`  | Non-HAL fallback (OpenAI / public results)     | Confirms gates aren't HAL-specific                          |

### Non-HAL fallback choice (task 1.4)

**Selected fallback: `browsecomp`** (default per the design's open question).

If, during scouting, BrowseComp's public artifact turns out to expose only aggregate leaderboard numbers with no per-task or per-run granularity, downgrade gate 1 (run-level data) to fail and document this in the candidate's `columns.json`. Do **not** silently swap to a different non-HAL source mid-scout — instead, record the failure, complete the inventory with whatever is available, and proceed. The decision document records gate failures, not just successes.

## Conventions

- Outputs in `candidates/<candidate>/` and `synthetic/` are the contract. Treat them as immutable once `gaia-hal-generalist-decision.md` is written.
- `provenance.json` is the regeneration recipe. If you can't re-fetch and re-sample from `provenance.json` alone, the file is incomplete.
- Parquet preferred over CSV for samples (smaller, faster, schema-preserving). CSV permitted only if Parquet is impractical for a specific source.
- Sample files capped at 5 MB. Larger samples must be downsampled with a recorded seed.

## Read also

- [scouting/gaia-hal-generalist-decision.md](gaia-hal-generalist-decision.md)
- [scouting/tau-bench-airline-tool-calling-decision.md](tau-bench-airline-tool-calling-decision.md)
- [reports/cross-harness-confound/notes.md](../reports/cross-harness-confound/notes.md)
