.PHONY: test lint format analyze report

test:
	uv run pytest

lint:
	uv run ruff check rigor tests

format:
	uv run ruff format rigor tests

analyze:
	uv run rigor analyze studies/exhibit-a.yaml

report:
	uv run rigor report studies/exhibit-a.yaml
