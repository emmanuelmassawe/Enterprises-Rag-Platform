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

## Milestone 5 evidence (2026-11-16)

| Area | Evidence | Result |
|---|---|---|
| Static quality | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run lint-imports` | Passed after final source changes. |
| Unit and red-team behavior | `uv run coverage run -m pytest -q -p no:cacheprovider --basetemp=C:/Users/EMMA/AppData/Local/Temp/rag-m5-pytest-20261116-r5`; `uv run coverage report --fail-under=80` | 103 passed; branch-aware coverage 83%, passed. An earlier run exposed a test fake without the optional Gemini `candidates` field; the adapter now handles that missing field, and the final full suite passes. |
| Privacy and tracing | Synthetic tests verify redaction, allowlisted metadata, empty model inputs/outputs, nested LangSmith stage runs, run correlation and sampling; no provider credentials used | Provider-free tests; no external LangSmith payload or outage test was run. |
| Security smoke | `uv run pytest -q -p no:cacheprovider tests/security` | 5 synthetic direct/indirect, Base64, Swahili, hidden Unicode and markup/canary cases passed. GNU `make` is unavailable in the Windows shell, so the Makefile recipe was run directly. Live-model ASR is not measured. |
| Local observability | `docker compose --profile observability config --quiet`; `docker compose build api worker` | Compose configuration parsed and hardened API/worker images built. Profile services were not started; Grafana alert delivery is not verified. |
| Load baseline | `make load-test` requires a synthetic tenant/collection and non-production API key | Not run; no staging target or credentials were provided. |
| Dependency/security audit | `uv lock`; `uv sync --all-groups --locked`; `uv run pip-audit --skip-editable` | Lock resolves and sync succeeds; pip-audit found no known vulnerabilities. The editable project distribution was skipped by design. |
| External services | No live Gemini, LangSmith or Grafana Cloud credentials used | Not exercised. LangSmith remains disabled by default. |

M5 implementation is committed in `1798f2d`, `c070409`, and `de0abcc`; this evidence update and final tests follow those commits. Remaining owner and staging release gates are listed in [ADR-015](ADR/ADR-015-milestone-5-observability-security.md) and [AI security](AI_SECURITY.md).

## Milestone 6 evidence (2026-11-16)

| Area | Evidence | Result |
|---|---|---|
| Evaluation implementation | Versioned synthetic golden set, pure recall@k/MRR/nDCG/citation/refusal scoring, structured Gemini judge, optional LangSmith `evaluate()` experiment and `make eval` threshold gate | Implemented; report and thresholds remain baseline-only until owner approves numeric floors. |
| Dataset and target | `tests/eval/golden_dataset.json`; existing admin debug query endpoint with synthetic benchmark chunk IDs | No staging endpoint, benchmark collection or credentials were available, so the end-to-end evaluation and live LangSmith experiment were not run. |
| Provider/API verification | Current official LangSmith evaluate reference, LangSmith evaluation guidance, Google GenAI SDK and structured output references recorded in ADR-016 | Checked 2026-11-16. |
| Static quality | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run lint-imports` | Passed; 126 files formatted, 66 source files type-checked, both import contracts kept. |
| Unit behavior and coverage | `uv run coverage run -m pytest -q -p no:cacheprovider --basetemp=C:/Users/EMMA/AppData/Local/Temp/rag-m6-pytest-20261116-r2`; `uv run coverage report --fail-under=80` | 107 passed; 83% branch-aware coverage; passed. The 4 new evaluation tests used no network or model calls. |
| Diff integrity | `git diff --check` | Passed. |
| End-to-end evaluation | `make eval` with configured non-production benchmark endpoint, admin key, collection and Gemini judge credentials | Not run; no staging endpoint, benchmark collection or credentials were available. |

M6's synthetic dataset and provider setup assumptions are documented in [the evaluation guide](EVALUATION.md) and [ADR-016](ADR/ADR-016-milestone-6-evaluation-harness.md). The end-to-end evaluation remains an owner/operator setup gate; unset thresholds do not assert quality.

## Milestone 8 evidence (2026-11-17)

| Area | Evidence | Result |
|---|---|---|
| Web implementation | Next.js App Router, Google OIDC BFF, server-side identity map, chat/SSE, citations, collection/document/admin screens, EN/SW catalogs, responsive theme tokens, Faro | Implemented in `web/`; no production or staging identity/data used. |
| Security-sensitive dependencies | `npm audit --json` using current npm registry advisories | Initial pinned versions reported six advisories. Upgraded Next.js, Auth.js, next-intl, PostCSS and Zod; regenerated lockfile. Subsequent locked install/audit is pending because registry download timed out. |
| Python static gates | `uv run ruff check src`; `uv run ruff format --check src`; `uv run mypy src`; `uv run lint-imports` | Ruff lint passed; strict mypy passed on 70 source files; both architecture contracts kept. Ruff format found pre-existing changed-file formatting and it was corrected; final full format check pending. |
| Terraform | Terraform 1.17.2 `fmt -recursive`; `init -backend=false`; `validate` with Render 1.9.1/Grafana 4.45.2, full repository mounted | Passed. An initial validate with only `infra/terraform` mounted correctly exposed that existing dashboard/Alloy `file()` references require the full repository; rerun with the full repo passed. No plan/apply was run. |
| Frontend quality | `npm ci`, `npm audit`, ESLint, strict TypeScript and production build | Not complete: npm registry tarball request timed out on `zod-validation-error`; retry with persistent cache and extended retries is still running. |
| Browser and accessibility | Playwright, axe, Lighthouse, visual screenshots | Not run. No approved non-production Google identity or staging URL is configured; do not bypass sign-in or use customer data to fabricate screenshots. |
| API integration / deployment | Terraform plan/apply, live Google OIDC, Faro collector and RAG API | Not run; deployment secrets, identity map, selected origin and provider accounts are owner-managed inputs. |

Milestone 8 is implementation-complete but not production-ready. Do not infer WCAG conformance, Lighthouse budgets, deployed availability or end-to-end login from the code alone.

## Remaining release gates

- Confirm proposed `gemini-embedding-2` and 768 dimensions, account region, retention and spend limits; add a dimension-specific vector index in a new approved migration and benchmark it with tenant filters.
- Add real-adapter contract tests for database repositories and Redis, and broader RLS adversarial coverage. Current local unit tests use deterministic fakes for adapter methods; CI and local PostgreSQL RLS smoke checks verify tenant visibility, forced policies and denied cross-tenant inserts.
- Run the full CI workflow, dependency-failure fault injection, and a populated-schema migration/restore drill before claiming the production standard. Local `pip-audit --skip-editable` completed with no known vulnerabilities.
- Define a scheduled cleanup for expired idempotency records if issuance volume makes the bounded on-issuance cleanup insufficient.
- Configure production runtime/migration roles and database TLS/private URLs; the local trust-authenticated Compose network is development-only.
- Complete production readiness and owner go/no-go review. Image-only PDF OCR remains unsupported. Collection management and BFF session authorization are implemented, but their browser and staging evidence remains open.
