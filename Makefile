.PHONY: setup lock-check test slow verify lint lint-imports fix format format-check typecheck check

setup: lock-check
	uv sync --locked --extra dev

lock-check:
	uv lock --check

test:
	uv run --locked pytest -n auto

VERIFY_APP := .agents/skills/verify-eval-audit/verify

slow:
	uv run --locked pytest -n auto -m verify
	$(VERIFY_APP) all
	$(VERIFY_APP) control

# Drive the real CLI: no ARGS = drives for changed files; ARGS=all|list|control|<drive>.
verify:
	$(VERIFY_APP) $(ARGS)

lint:
	uv run --locked ruff check .

lint-imports:
	uv run --locked lint-imports

fix:
	uv run --locked ruff check --fix .
	uv run --locked ruff format .

format:
	uv run --locked ruff format .

format-check:
	uv run --locked ruff format --check .

typecheck:
	uv run --locked basedpyright
	uv run --locked python tools/baseline_ratchet.py

check: lock-check lint lint-imports format-check typecheck test
