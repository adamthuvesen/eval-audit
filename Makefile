.PHONY: test lint format format-check typecheck check analyze report

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run pytest

analyze:
	uv run eval-audit analyze studies/gaia-hal-generalist.yaml

report:
	uv run eval-audit report studies/gaia-hal-generalist.yaml
