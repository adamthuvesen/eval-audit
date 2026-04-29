# Cross-harness confound on TAU-bench Airline

> Same model, same benchmark, two harnesses, 12 percentage points apart.

Claude 3.7 Sonnet on **TAU-bench Airline** sits at **44%** under the public Tool Calling harness and at **56%** under the HAL Generalist Agent harness. The benchmark is the same 50-task airline set; the model is the same; the gap is the harness.

That gap is roughly the size of the difference between two different frontier models — but it is *not* a model effect. The TAU-bench public leaderboard mixes Tool Calling, HAL Generalist, and TAU few-shot rows in a single ranking, so a reader doing model selection from the leaderboard cannot tell whether a higher row reflects the *model* or the *scaffold the model was wrapped in*.

This writeup pulls the Tool Calling number from our Exhibit B reanalysis (data) and **cites** the HAL Generalist number from the upstream leaderboard (public record we trust but did not re-derive).

## The two numbers

**Tool Calling: 44%.** From [`reports/exhibit-b/analysis.json`](../exhibit-b/analysis.json), produced by `rigor analyze studies/exhibit-b.yaml`. Reproducible:

```python
import json
result = json.load(open("reports/exhibit-b/analysis.json"))
claude = next(
    a for a in result["per_agent"]
    if a["agent_id"] == "Taubench ToolCalling (claude-3.7-sonnet)"
)
print(f"{claude['success_rate']:.4f}")  # -> 0.4400 (22/50, errored counts as failure)
```

This is the leaderboard-matching figure: 50 tasks, 22 graded successes, 25 graded failures, 3 upstream errors that the toolkit folds in as failures (the same convention the public leaderboard uses).

**HAL Generalist: 56%.** Cited from [`scouting/candidates/tau-bench/provenance.json`](../../scouting/candidates/tau-bench/provenance.json), `leaderboard_cross_check[1].note`:

> The leaderboard's '56% / $42.11' Claude 3.7 Sonnet entry is the HAL Generalist Agent harness, NOT Tool Calling — see scouting_lessons.cross_harness_confound below.

Reproducible:

```python
import json
prov = json.load(open("scouting/candidates/tau-bench/provenance.json"))
# Locate the Claude 3.7 Sonnet entry under TAU-bench Tool Calling.
entry = next(
    e for e in prov["leaderboard_cross_check"]
    if "Claude 3.7 Sonnet" in e["agent"] and "Tool Calling" in e["agent"]
)
# The note pinpoints which leaderboard row the 56% figure belongs to.
print(entry["note"])
```

We do **not** re-derive 56% from a local fixture: HAL's TAU-bench Generalist Agent traces are not in `scouting/candidates/`. We accept the leaderboard's reported figure as a citation, anchored to the scouting commit so the cite stays auditable.

## The framing

The 12 pp gap is best read as **a scaffold effect coexisting with sampling-decision differences the public leaderboard does not separate**. HAL's Generalist Agent harness and the Tool Calling harness are not just two wrappers around the same call sequence; they differ in `reasoning_effort`, prompt boilerplate, retry policy, tool-result handling, and (likely) other knobs that the upstream leaderboard reports under the same model name. Some of the 12 pp is scaffold; some is sampling-decision drift baked into "scaffold". The leaderboard does not separate those.

What the writeup *does* claim:

- Within the same benchmark (TAU-bench Airline, 50 tasks), the same model (Claude 3.7 Sonnet) lands at 44% under one harness and 56% under another.
- Treating leaderboard rows as model-only effects when the rows mix harnesses is a category error that costs you ~12 pp of accuracy reading.
- Decision-makers picking a model off a public leaderboard need to first ask "under which scaffold?" before the rank order is interpretable.

What the writeup does *not* claim:

- That the 12 pp is "scaffold effect, full stop." HAL's two harnesses likely also differ in reasoning effort, prompt layout, and retry budget — confounds the leaderboard does not break out.
- That HAL Generalist is "better" or "worse" than Tool Calling. Better/worse is downstream of which scaffold matches the deployment context.

## Why this matters for `rigor`

This is the project's strongest scouting finding. The toolkit's response is procedural: every study spec is locked to a single harness; the analyze step refuses to compare agents across harnesses (`CrossHarnessComparisonError`). A user trying to cross harnesses inside a `StudySpec` is told to open a separate change. The writeup above is what the procedural rule is *protecting against*: it is one number on a leaderboard, and changing the scaffold changes it by ~12 pp without changing the model.

The same-benchmark, cross-harness comparison is the only honest framing. The reverse — comparing Exhibit A (GAIA, HAL Generalist) to Exhibit B (TAU-bench, Tool Calling) — would mix a benchmark difference with a scaffold difference and tell the reader nothing.

---

## Last derived from

- **Exhibit B `analysis.json` sha256:** `6880efa90ef384a310cc045b7f4eb8ffd98327ae678ec4b92230358c6a58c224`
- **Cited scouting provenance entry:** [`scouting/candidates/tau-bench/provenance.json`](../../scouting/candidates/tau-bench/provenance.json), JSON path `leaderboard_cross_check[1].note`
- **Date:** 2026-05-02
