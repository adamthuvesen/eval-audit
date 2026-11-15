# Report design rules

Markdown rendering, decision rules, and sensitivity tables live in
[eval_audit/report](../eval_audit/report). Committed reports are checked against a fresh render by
[tests/report/test_committed_reports.py](../tests/report/test_committed_reports.py).

- Reports are decision artifacts. They should tell a model selector what to do,
  not stop at the numbers.
- Keep output deterministic: stable ordering, stable formatting, stable clocks
  in tests, and reviewed committed reports.
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


## One audit workflow

`pipeline.build_audit` prepares evidence once, computes one analysis, and creates artifact bytes.
Both `audit` and `report` use this workflow. Publication belongs to `artifacts.py`.
The installed CLI does not import or execute pytest.
`--skip-validation` remains a deprecated no-op. Evidence validation always runs.
Synthetic recovery belongs to development verification, including `make check`.

`AnalysisResult.settings` is authoritative for inference settings.
Rendering rejects conflicting study IDs, alpha values, bootstrap seeds, or iteration counts.
`EvidenceSource` names the actual loaded file. Canonical input does not inherit adapter receipts.
Residual-risk documents use explicit evidence bindings, including the committed HumanEval exhibit.
Missing residual-risk documentation is visible in readiness and the report.

`summary.json` retains schema version 1 and existing artifact filenames.
Readers reject unsupported versions, nonfinite numbers, unknown verdicts, inconsistent claims,
unsafe references, and changed artifact hashes. Invalid historical summaries require regeneration.
`analysis.json` adds `settings` and retains the legacy top-level `bootstrap_seed`.

See [architecture](architecture.md) for publication state and ownership.
