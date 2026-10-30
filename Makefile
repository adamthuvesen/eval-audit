.PHONY: setup lock-check test verify lint lint-imports format format-check typecheck check analyze report

# Slow suites: subprocess wheel install and simulation-heavy recovery gates.
VERIFY_TESTS := tests/packaging tests/synthetic_validation

setup: lock-check
	uv sync --locked --extra dev

lock-check:
	uv lock --check

test:
	uv run --locked pytest -n auto $(addprefix --ignore=,$(VERIFY_TESTS))

verify:
	uv run --locked pytest -n auto $(VERIFY_TESTS)

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

analyze:
	uv run --locked eval-audit analyze studies/gaia-hal-generalist.yaml

report:
	uv run --locked eval-audit report studies/gaia-hal-generalist.yaml
