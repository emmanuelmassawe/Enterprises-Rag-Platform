.PHONY: setup dev test lint typecheck web-setup web-lint web-typecheck web-build smoke security-audit migrate bootstrap eval redteam load-test tf-plan tf-apply

setup:
	uv sync --all-groups

dev:
	docker compose up -d db state cache
	docker compose --profile tools run --rm migrator
	docker compose up --build api worker

test:
	uv run coverage run -m pytest
	uv run coverage report --fail-under=80

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src
	uv run lint-imports

web-setup:
	cd web && npm ci --ignore-scripts

web-lint:
	cd web && npm run lint

web-typecheck:
	cd web && npm run typecheck

web-build:
	cd web && npm run build

smoke:
	uv run python scripts/smoke.py

security-audit:
	uv run pip-audit --skip-editable

migrate:
	docker compose --profile tools run --rm migrator

bootstrap:
	docker compose --profile tools run --rm migrator python -m rag.db.bootstrap --tenant-name "$(TENANT_NAME)"

# These targets are activated in the milestones that introduce their tools and data.
eval:
	uv run python scripts/evaluate.py

tf-plan:
	terraform -chdir=infra/terraform fmt -check -recursive
	terraform -chdir=infra/terraform init -input=false -backend-config=envs/backend.hcl
	terraform -chdir=infra/terraform validate
	terraform -chdir=infra/terraform plan -input=false

# Applies are performed only by the protected CI/CD workflow. This target is intentionally unavailable.
tf-apply:
	@echo "Terraform apply is CI-only; use the protected staging or production workflow."
	@exit 2

# Synthetic, provider-free smoke attacks for pull requests and local work.
redteam:
	uv run pytest -q -p no:cacheprovider tests/security

# Requires explicit credentials and a synthetic tenant/collection on a non-production target.
load-test:
	uv run python scripts/load_test.py

