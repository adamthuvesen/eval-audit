.PHONY: setup lock-check test verify drive lint lint-imports format format-check typecheck check

setup: lock-check
	uv sync --locked --extra dev

lock-check:
	uv lock --check

test:
	uv run --locked pytest -n auto

VERIFY_APP := .agents/skills/verify-eval-audit/verify

verify:
	uv run --locked pytest -n auto -m verify
	$(VERIFY_APP) all
	$(VERIFY_APP) control

# Drive the real CLI: no ARGS = drives for changed files; ARGS=all|list|control|<drive>.
drive:
	$(VERIFY_APP) $(ARGS)

lint:
	uv run --locked ruff check .

lint-imports:
	uv run --locked lint-imports

format:
	uv run --locked ruff format .

format-check:
	uv run --locked ruff format --check .

typecheck:
	uv run --locked mypy

check: lock-check lint lint-imports format-check typecheck test
