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
work, run `make check` and `make verify`.

## Snapshots

Report snapshots are expected artifacts, not incidental churn. Update them
only when the rendered change is intended and you have reviewed the diff:

```bash
UPDATE_SNAPSHOTS=1 uv run pytest tests/report/test_snapshot.py
```

## Test lanes

`make check` is the fast lane and the first CI job. It runs lock, lint,
import-contract, format, and type checks, then pytest in parallel through
pytest-xdist. It skips the directories in the Makefile `VERIFY_TESTS` list.

`make verify` is the slow lane and the second CI job. It runs only the
`VERIFY_TESTS` directories:

- `tests/packaging/`: sdist hygiene and the installed-wheel workflow.
- `tests/synthetic_validation/`: recovery and finite-sample calibration
  against `scouting/synthetic/`.

To add a slow suite, add its directory to `VERIFY_TESTS`.

## Locked developer setup

Use `make setup` to check the lockfile and install development dependencies with `uv sync --locked --extra dev`.
Run focused suites with `uv run --locked pytest <path>`.

The wheel test builds a wheel and installs it in a temporary virtual environment outside the checkout.
It exports exact runtime artifacts from `uv.lock` through `pylock.toml` and installs cached artifacts offline.
Run `make setup` first to populate the cache for the current interpreter and platform.
The environment excludes development dependencies and verifies that `pytest` is absent.
The test exercises version, relative-path init, validate, audit, report, gate, and portfolio commands.

## Public fixture regeneration

Fixture tools default to offline replay. Replay requires a local cache with `manifest.json` and hashed source bytes.
Replay checks source hashes and preserves the refresh timestamp.
The historical committed fixtures do not include these source caches.
Their provenance alone cannot supply a complete offline replay.

```bash
uv run --locked python tools/regenerate_swe_bench_verified.py \
  --cache-dir .scout-cache/swe-pinned --output-dir /tmp/swe-replay
uv run --locked python tools/regenerate_terminal_bench_mux.py \
  --cache-dir .scout-cache/terminal-pinned --output-dir /tmp/terminal-replay
```

Refresh requires `--mode refresh` and a full dataset commit SHA through `--revision`.
The SWE-bench tool also requires the experiments repository commit SHA through `--experiments-revision`.
Refresh fetches only revision-pinned URLs, with a 30-second request timeout.
Use a separate cache directory for each source revision.
Review candidate output in a separate `--output-dir` before replacing canonical evidence.
Any differing existing fixture requires `--accept-evidence-change`, including during replay.
Rerun affected reports and review their evidence after an accepted change.

Each tool stages parquet and provenance, then validates the staged pair before canonical promotion.
A failed replacement restores files already replaced by that operation.
Pair replacement is not crash-atomic. Do not run concurrent readers or writers during promotion.
Offline tests cover corrupt cache bytes, invalid task IDs, missing usage, missing timestamps, and partial replacement failures.

## Historical HumanEval tooling

The historical grader CLI refuses model-completion execution because it has no isolated execution backend.
A sanitized environment, Python `-I`, temporary directory, and timeout do not provide containment.
The private subprocess helper accepts only repository-authored test fixtures.
Its completion receipt prevents an early `sys.exit(0)` from counting as a completed test.
The receipt is a correctness check, not a security boundary.
Tests distinguish candidate failures, timeouts, incomplete execution, and infrastructure errors.

The normalizer rejects unknown token usage, missing timestamps, and historical grades without completion receipts.
It derives canonical columns from `RunRecord` and validates staged parquet before replacement.
Existing recorded grades, fixtures, and reports retain their historical evidence meaning.
These checks do not revalidate historical grades or provide an isolated execution backend.
