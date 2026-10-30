.PHONY: setup lock-check test test-cli test-packaging test-scouting test-snapshots test-synthetic lint format format-check typecheck check analyze report

setup: lock-check
	uv sync --locked --extra dev

lock-check:
	uv lock --check

test:
	uv run --locked pytest

test-cli:
	uv run --locked pytest tests/cli

test-packaging:
	uv run --locked pytest tests/packaging

test-scouting:
	uv run --locked pytest tests/scouting

test-snapshots:
	uv run --locked pytest tests/report/test_snapshot.py

test-synthetic:
	uv run --locked pytest -m synthetic_validation tests/synthetic_validation

lint:
	uv run --locked ruff check .

format:
	uv run --locked ruff format .

format-check:
	uv run --locked ruff format --check .

typecheck:
	uv run --locked mypy

check: lock-check lint format-check typecheck test

analyze:
	uv run --locked eval-audit analyze studies/gaia-hal-generalist.yaml

report:
	uv run --locked eval-audit report studies/gaia-hal-generalist.yaml
