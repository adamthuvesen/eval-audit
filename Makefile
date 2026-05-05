.PHONY: test lint format check analyze report

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format eval_audit tests

check:
	uv run pytest
	uv run ruff check .

analyze:
	uv run eval-audit analyze studies/gaia-hal-generalist.yaml

report:
	uv run eval-audit report studies/gaia-hal-generalist.yaml
