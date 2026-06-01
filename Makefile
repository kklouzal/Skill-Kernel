.PHONY: test lint compile plugin-check

test:
	uv run pytest

lint:
	uv run ruff check sidecar

compile:
	uv run python -m compileall sidecar

plugin-check:
	cd plugin/autoskill && npm run check

