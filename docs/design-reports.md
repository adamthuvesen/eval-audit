# Report design rules

Markdown rendering, decision rules, and sensitivity tables live in
[eval_audit/report](../eval_audit/report). Output is snapshot-tested by
[tests/report/test_snapshot.py](../tests/report/test_snapshot.py).

- Reports are decision artifacts. They should answer what a model selector
  should do, not just list numbers.
- Keep output deterministic: stable ordering, stable formatting, stable clocks
  in tests, and reviewed snapshots.
- Surface caveats near the claims they affect. Do not bury cost or provenance
  caveats in generic footnotes.
- The allowed decision vocabulary is intentional: `switch`, `hold`,
  `drop_from_shortlist`, `rerun_more_n`, `hedge_on_cost`, and
  `inconclusive_no_action`.

## CLI

The Typer CLI ([eval_audit/cli.py](../eval_audit/cli.py)) should stay minimal
and reproducible.

- CLI failures should be clear, non-zero, and tied to the invalid input or
  failed validation gate.
- Do not add network-dependent CLI paths without an explicit user request and
  a reproducibility story.
