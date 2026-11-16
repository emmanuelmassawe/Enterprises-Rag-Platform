# Production readiness evidence

This file records completed checks and unresolved release gates. Passing a local M2 check does not certify the platform for production.

## Milestone 2 evidence (2026-11-16)

| Area | Evidence | Result |
|---|---|---|
| Static quality | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run lint-imports` | Passed. |
| Unit behavior | API-key lifecycle, authorization, rate-limit fallback, transaction-local identity, Postgres adapter behavior, health and configuration tests | 25 passed. One dependency deprecation warning from Starlette's TestClient integration with httpx. |
| Coverage | `uv run coverage run -m pytest`; `uv run coverage report --fail-under=80` | 86%, passed. Declarative SQLAlchemy mappings and Alembic's environment entrypoint are excluded because their behavior is verified by migration/DB checks. |
| Empty database migration | `alembic upgrade head` on a fresh isolated pgvector/Postgres database | Passed. Created all 11 tenant-scoped tables and forced RLS. |
| Tenant isolation | Runtime role selected one of two synthetic tenants with `app.tenant_id`; cross-tenant insert attempted | One tenant visible; cross-tenant insert rejected by RLS. |
| Populated migration rerun | Re-applied `alembic upgrade head` after inserting two synthetic tenant rows | Passed; both synthetic rows remained. |
| Runtime role | `rag_runtime` uses `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`, `NOBYPASSRLS`; separate `rag_migrator` handles schema | Verified in local Compose schema and grants. |
| Container image and HTTP health | `docker compose build api`; in-container requests to `/healthz` and `/readyz` | Build passed; liveness returned `ok` and readiness returned `ready`. |

## Remaining release gates

- Choose and approve the embedding model and vector dimension; add the dimension-specific vector index in a new approved migration and benchmark it with tenant filters.
- Add real-adapter contract tests for database repositories and Redis, and broader RLS adversarial coverage. Current local unit tests use deterministic fakes for adapter methods; CI and local PostgreSQL RLS smoke checks verify tenant visibility, forced policies and denied cross-tenant inserts.
- Run the full CI workflow, dependency-failure fault injection, and a populated-schema migration/restore drill before claiming the production standard. Local `pip-audit --skip-editable` completed with no known vulnerabilities.
- Define a scheduled cleanup for expired idempotency records if issuance volume makes the bounded on-issuance cleanup insufficient.
- Configure production runtime/migration roles and database TLS/private URLs; the local trust-authenticated Compose network is development-only.
- Complete remaining milestones for ingestion, retrieval, AI safety, observability, evaluations, Terraform, web UI, and go/no-go review.
