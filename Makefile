.PHONY: setup dev test lint typecheck smoke security-audit migrate eval redteam load-test tf-plan tf-apply

setup:
	uv sync --all-groups

dev:
	uv run uvicorn rag.api.main:app --app-dir src --host 127.0.0.1 --port 8000 --reload

test:
	uv run coverage run -m pytest
	uv run coverage report --fail-under=80

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src
	uv run lint-imports

smoke:
	uv run python scripts/smoke.py

security-audit:
	uv run pip-audit --skip-editable

# These targets are activated in the milestones that introduce their tools and data.
migrate eval redteam load-test tf-plan tf-apply:
	@echo "$@ is not available yet; it will be enabled in the milestone that introduces it."
	@exit 2

