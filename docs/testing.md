# Testing expectations

Match test scope to risk:

- **Schema changes:** schema tests, invalid-case tests, and CLI validation
  tests.
- **Ingest changes:** adapter tests plus provenance/cost-path tests.
- **Statistical changes:** unit tests, property tests where useful, and
  synthetic recovery validation when behavior could affect conclusions.
- **Report changes:** renderer tests, decision-impact tests, sensitivity tests,
  and snapshot review.
- **CLI changes:** command tests and at least one realistic study path.

For report-affecting work, run the snapshot test. For methodology-affecting
work, run `make check` plus the synthetic-validation gate when relevant.

## Snapshots

Report snapshots are expected artifacts, not incidental churn. Update them
only when the rendered change is intended and you have reviewed the diff:

```bash
UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py
```

## Synthetic-validation gate

The `synthetic_validation` marker runs end-to-end recovery checks against
`scouting/synthetic/`. Run it for methodology-affecting work:

```bash
uv run pytest -m synthetic_validation tests/synthetic_validation
```
