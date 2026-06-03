.PHONY: test lint compile plugin-check observatory-build worker-maintenance worker-scheduler

test:
	uv run pytest

lint:
	uv run ruff check sidecar

compile:
	uv run python -m compileall sidecar

plugin-check:
	cd plugin/autoskill && npm run check

observatory-build:
	cd sidecar/autoskill/observatory && npm ci && npm run build

worker-maintenance:
	PYTHONPATH=sidecar uv run python -m autoskill.worker_main --pool maintenance

worker-scheduler:
	PYTHONPATH=sidecar uv run python -m autoskill.worker_main --pool scheduler
