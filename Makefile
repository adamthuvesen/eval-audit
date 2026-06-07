.PHONY: test lint format format-check check analyze report

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

analyze:
	uv run eval-audit analyze studies/gaia-hal-generalist.yaml

report:
	uv run eval-audit report studies/gaia-hal-generalist.yaml
