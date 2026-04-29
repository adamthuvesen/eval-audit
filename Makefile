.PHONY: test lint format check analyze report

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format rigor tests

check:
	uv run pytest
	uv run ruff check .

analyze:
	uv run rigor analyze studies/exhibit-a.yaml

report:
	uv run rigor report studies/exhibit-a.yaml
