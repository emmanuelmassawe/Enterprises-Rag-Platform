# Production readiness evidence

This file records completed checks and unresolved release gates. Passing a local milestone check does not certify the platform for production.

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
| Redis local services | `state` and `cache` health probes and `CONFIG GET` | Both responded `PONG`; state reports `noeviction`, cache reports `allkeys-lru` with 134217728-byte cap. |
| Container image and HTTP health | `docker compose build api`; in-container requests to `/healthz` and `/readyz` | Build passed; liveness returned `ok` and readiness returned `ready`. |

## Milestone 3 evidence (2026-11-16)

| Area | Evidence | Result |
|---|---|---|
| Static quality | `ruff check .`; `ruff format --check .`; `mypy src`; `lint-imports` | Passed. The domain and API layer contracts remain intact. |
| Unit behavior and coverage | `coverage run -m pytest -q`; `coverage report --fail-under=80` | 67 passed; 81% branch-aware coverage; one Starlette/httpx deprecation warning. |
| Empty and populated migration | `docker compose --profile tools run --rm migrator` applied the schema; repeat upgrade and `alembic check` against the populated local database | Passed; repeat upgrade was a no-op and Alembic reported no new upgrade operations. |
| Quarantine database policy | Local Postgres query checked `relrowsecurity`, `relforcerowsecurity`, and `rag_runtime` DML grant on `quarantine_decisions` | All three true. Migration also creates the tenant-scoped audit table and forced RLS policy. |
| API/worker/migrator images | `docker compose build api worker migrator` | Passed with the hardened non-root, read-only container images. |
| Dependency audit | `pip-audit --skip-editable` using the current PyPI vulnerability database | No known vulnerabilities found; the editable project package was skipped by design. |
| Provider integration | No live Gemini or production S3 credentials were used | Not exercised. Unit tests use deterministic provider/storage fakes. |

The local review endpoints require admin API-key scope, expose plain text only, and record an idempotent decision with actor, reason, and tenant identity. The heuristic scanner is only triage; it is not a safety guarantee. Production data must not be sent to Gemini until the proposed model, dimension, region, retention and spend limits are confirmed.

## Milestone 4 evidence (2026-11-16)

| Area | Evidence | Result |
|---|---|---|
| Static quality | `ruff check .`; `ruff format --check .`; `mypy src`; `lint-imports` | Passed. Domain and API layer contracts kept. |
| Query behavior | Full suite covering RRF, refusal, citation validation, sanitization, cache fallback/epoch, provider schema and SSE | 89 passed; one Starlette/httpx deprecation warning. |
| Coverage | `coverage run -m pytest -q -p no:cacheprovider --basetemp=.m4-test-tmp`; `coverage report --fail-under=80` | 83% branch-aware coverage; passed. |
| Database migration | Local Compose migrator applied `c51b6d27e940`; `alembic check` | Passed; no schema drift detected on the existing populated local database. A fresh empty-database run was not repeated in M4. |
| Container images | `docker compose build api worker migrator` | Passed. |
| Provider integration | No live Gemini key or production data used | Not exercised; only deterministic tests. |
| Performance | No model-pinned staging environment/load test available in M4 | Not measured; full generation completes before first answer event, so the proposed TTFT SLO remains at risk. |
| API stream | JSON/SSE TestClient contract, event sequence, refusal shape and one terminal event | Passed. |
| OpenAPI Spectral | Approved `api/openapi.yaml` was unchanged in M4 | Not rerun; Node/Spectral is not installed in this workspace. |

M4's proposed `gemini-3.8-flash`, query similarity/context thresholds, cache TTL and generation token/concurrency limits require owner confirmation. See [ADR-014](ADR/ADR-014-milestone-4-query-pipeline.md).

## Remaining release gates

- Confirm proposed `gemini-embedding-2` and 768 dimensions, account region, retention and spend limits; add a dimension-specific vector index in a new approved migration and benchmark it with tenant filters.
- Add real-adapter contract tests for database repositories and Redis, and broader RLS adversarial coverage. Current local unit tests use deterministic fakes for adapter methods; CI and local PostgreSQL RLS smoke checks verify tenant visibility, forced policies and denied cross-tenant inserts.
- Run the full CI workflow, dependency-failure fault injection, and a populated-schema migration/restore drill before claiming the production standard. Local `pip-audit --skip-editable` completed with no known vulnerabilities.
- Define a scheduled cleanup for expired idempotency records if issuance volume makes the bounded on-issuance cleanup insufficient.
- Configure production runtime/migration roles and database TLS/private URLs; the local trust-authenticated Compose network is development-only.
- Complete retrieval, AI safety, observability, evaluations, Terraform, web UI, and go/no-go review. Image-only PDF OCR remains unsupported; collection management and BFF session authorization are future milestones.
