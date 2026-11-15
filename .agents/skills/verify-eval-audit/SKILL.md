---
name: verify-eval-audit
description: "Drives the real eval-audit CLI (audit, init, validate, the cross-harness refusal) against committed fixtures in temp dirs. Use to run, launch, drive, or verify eval-audit, or to prove a change to it works."
---

# Verify eval-audit

`verify` runs the installed `.venv/bin/eval-audit` console script the way a user does. It audits `examples/byo-minimal`, follows the `init` scaffold's own README steps, and checks that a cross-harness claim is refused. Every output goes to a temp dir with a temp HOME. Nothing is written to `reports/`. Tripwire shims for network and install commands (`curl`, `uv`, `pip`, and others) lead PATH, and HTTP proxies point at a dead port, so a drive that tries to reach the network fails.

## Run

From the repo root, after `make setup`:

- `make verify` after a change. It runs the drives whose paths match files changed against the merge base with `main`, plus uncommitted and untracked files. With no match it runs the smoke drive.
- `make verify ARGS=all` before handing over larger work. `make slow` (the CI slow lane) also runs `all` and `control` after the `verify`-marked pytest suite.
- `make verify ARGS=list` shows each drive, what it proves, and the paths it covers.
- `make verify ARGS="audit refusal"` runs named drives.
- `make verify ARGS=control` re-drives the smoke drive against a wrong verdict. It exits 0 only when it observes FAIL.

You can also call `.agents/skills/verify-eval-audit/verify <args>` directly.

## Reading results

Each drive prints `PASS|FAIL <drive> <seconds>s <detail>`. A FAIL detail names the expected and the actual value, or the command's exit code and the tail of its output. The run ends with `evidence: .verify/runs/<utc>-<sha7>[-dirty]/`, which holds `preflight.log`, one `<drive>.<step>.json` per command (argv, cwd, env, exit, stdout, stderr), `audit.summary.json`, and `summary.json`. `summary.json` records the overall `result`. A run that changes the checkout (a tracked, untracked, or ignored file, the index, HEAD, or `.git/config` and hooks) adds `FAIL checkout` and fails. The helper does not retry, so it never reports `FLAKY`. A FAIL is a FAIL.

Preflight refuses to run when the locked environment does not resolve, when `eval_audit` imports from outside this checkout, or when the installed version differs from `pyproject.toml`.

## Limits

- Drives use 500 bootstrap iterations, not the default 10000. Committed reports and full-precision numbers stay with `make check` (fresh-render test) and `make slow`.
- Public-benchmark adapters that fetch from Hugging Face (`tools/regenerate_*.py`, scouting downloads) are out of scope. Run them by hand only when a change touches them.

## Gotchas

- Each CLI call costs about 1s of Python startup, more on a loaded machine. Keep drives to a few calls each.
- Pass `--out-dir` (or run inside a temp `--cwd`). The default `reports/` is the committed report tree, so a run without it overwrites committed artifacts.
