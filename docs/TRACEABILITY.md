# Requirements traceability

Status: M2-M5 have implementation evidence. M5 wires OTel request spans, metadata-only opt-in LangSmith runs, local Grafana/Prometheus metrics and AI security smoke cases. Nested LangSmith stages/feedback, cloud alert exercises and production privacy gates remain open. CI must keep all FR references and tests synchronized.

## Functional requirements

| Requirement | Component | Endpoint(s) | Test ID(s) | Monitoring / SLO |
|---|---|---|---|---|
| FR-ING-001 | Upload API, BlobStore, bounded PDF parser | POST `/v1/documents` | `test_req_fr_ing_001_upload_is_stored_and_enqueued_once`; API PDF and magic-byte tests | Upload rejects and worker completion logs live; counters planned |
| FR-ING-002 | ARQ worker, job repository, Redis queue; failed terminal jobs retained in DB for review/retry | POST `/v1/documents`; GET `/v1/jobs/{id}`; POST `/v1/jobs/{id}/retry`; DELETE job | Full-queue, queue rollback, retry, cancel, and worker idempotency tests | `rag_ingestion_jobs_total` and `rag_dead_letter_jobs_total`; queue age/depth still require Redis instrumentation |
| FR-ING-003 | Heuristic scanner, quarantined chunk state, admin review/audit API | document job; GET `/v1/admin/quarantine*`; POST `/v1/admin/quarantine/{id}` | `test_req_fr_ing_003_normalizes_hidden_unicode_and_quarantines_instructions`; `test_indirect_instruction_is_quarantined_during_chunking`; quarantine API/repository tests | `rag_ai_security_events_total{category="injection_detected"}`; quarantine review age still open |
| FR-ING-004 | pypdf page extraction, deterministic page-aware chunker | POST/GET `/v1/documents`; future POST `/v1/query` | `test_req_fr_ing_004_chunking_is_bounded_and_preserves_page_provenance`; PDF page-limit tests | Missing page metadata and citation resolution metrics planned |
| FR-ING-005 | Deletion job, BlobStore, repository cleanup | DELETE `/v1/documents/{id}` | Worker deletion idempotency and failure-retry tests | Deletion backlog/partial-failure metrics planned |
| FR-QRY-001 | `QueryService`, tenant-bound `PostgresQueryRepository`, Gemini embeddings, dense + English FTS + RRF | POST `/v1/query` | `test_req_fr_qry_001_hybrid_answer_records_latency`; Postgres query adapter tests | `rag_query_duration_seconds`, `rag_query_requests_total`; per-step retrieval histograms remain open |
| FR-QRY-002 | empty-retrieval refusal and provider refusal handling in `QueryService` | POST `/v1/query` | `test_req_fr_qry_002_empty_retrieval_returns_typed_refusal` | refusal rate/accuracy not yet exported; M6 evaluation planned |
| FR-QRY-003 | `rag.query.v1` SSE router; validated answer emitted after citations | POST `/v1/query` | `test_req_fr_qry_003_sse_obeys_event_order_and_one_terminal_event`; SSE refusal contract test | TTFT, stream duration and cancellations not yet exported; full generation before first answer chunk is a known risk |
| FR-CIT-001 | strict structured claims and retrieved-ID membership validation | POST `/v1/query` | `test_req_fr_cit_001_unknown_citation_becomes_refusal`; valid citation service test | citation validation counter not yet exported |
| FR-CIT-002 | random source boundary, injection detector, PII policy, output canary/secret scanner, HTML/image/URL sanitizer | POST `/v1/query` | `test_req_fr_cit_002_suspicious_question_is_refused_before_provider_call`; `test_canary_and_secret_output_are_blocked`; `tests/security/test_red_team.py` | `rag_ai_security_events_total`, `rag_ai_canary_leaks_total`; raw content excluded |
| FR-QRY-004 | tenant-keyed Redis cache, tenant epoch invalidation, citation recheck, fail-open fallback | POST `/v1/query`; worker ingestion/deletion; quarantine decision | `test_req_fr_qry_004_cache_failure_falls_back_to_query`; query-cache adapter epoch test | cache hit/failure counters not yet exported |
| FR-CNV-001 | Conversation service, RLS | `/v1/conversations*` | `test_req_fr_cnv_001_ownership` | authz failures, conversation CRUD errors |
| FR-CNV-002 | Message repository, retention | GET messages; DELETE conversation | `test_req_fr_cnv_002_pagination_retention` | message page latency, retention/deletion lag |
| FR-AUTH-001 | API-key auth service, Postgres key repository, bootstrap CLI | `/v1/admin/api-keys*`; all protected routes | `test_req_fr_auth_001_api_key_is_hashed_and_returned_once`; `test_req_fr_auth_001_invalid_and_insufficient_credentials_are_denied`; `test_req_fr_auth_001_revoke_and_expiry_invalidate_credentials`; `test_req_fr_auth_001_postgres_store_*` | API request status counts; key secrets never logged; auth failure dashboards remain planned |
| FR-AUTH-002 | Google OIDC, BFF, session store | BFF login/logout and API proxy | `test_req_fr_auth_002_session` | login failures, session errors; no identity labels |
| FR-AUTH-003 | Transaction-local DB tenant context, forced Postgres RLS, separate migration/runtime roles | tenant-scoped repositories | `test_req_fr_auth_003_database_sets_transaction_local_identity`; CI migration/RLS smoke with two synthetic tenants | CI verifies tenant visibility and cross-tenant insert denial; security event aggregation remains planned |
| FR-AUTH-004 | Redis fixed-window `RateLimiter`, bounded local fallback | `/v1/admin/api-keys*`; future protected query/upload/write endpoints | `test_req_fr_auth_004_memory_limiter_*`; `test_req_fr_auth_004_shared_limiter_uses_atomic_tenant_key_counter`; `test_req_fr_auth_004_limiter_uses_fallback_when_no_redis_is_configured` | Live `rag_rate_limit_fallback_total`; 429 status counts; quotas/cost anomaly remain planned |
| FR-KB-001 | Collection/document use cases and repositories | `/v1/collections*`; `/v1/documents` | `test_req_fr_kb_001_crud_scope` | CRUD errors, delete cascade age |
| FR-ADM-001 | Admin-scoped quarantine review API and `quarantine_decisions` audit table | GET `/v1/admin/quarantine*`; POST `/v1/admin/quarantine/{id}` | Quarantine API auth, decision idempotency and audit repository tests | Review queue depth/age/decision counters planned |
| FR-ADM-002 | Usage aggregation, API key service, status | `/v1/admin/usage`; `/v1/admin/api-keys*`; `/v1/admin/status` | `test_req_fr_adm_002_admin_scope` | usage/cost, admin endpoint errors |
| FR-FBK-001 | Feedback service, query correlation, LangSmith adapter | POST `/v1/feedback` | `test_req_fr_fbk_001_feedback` | feedback rate, export failure counter |
| FR-EVL-001 | `src/rag/domain/evaluation.py`, synthetic versioned golden set, Gemini judge and optional LangSmith experiment | Existing admin-only `POST /v1/query` debug response; offline scoring CLI `make eval` | `test_req_fr_evl_001_golden_eval`; deterministic metric unit tests | Local versioned JSON report; LangSmith experiment scores when enabled; owner-approved threshold failures |
| FR-USG-001 | Usage ledger, provider wrapper, quota service | POST query; GET admin usage | `test_req_fr_usg_001_accounting` | token/cost estimate, tenant quota events |
| FR-UI-001 | Web chat and citation renderer | query, feedback, conversation/messages | `test_req_fr_ui_001_chat_e2e` | Faro route/error/web vital; query SLO |
| FR-UI-002 | i18n/theme/responsive/a11y system | UI routes | `test_req_fr_ui_002_locale_a11y` | Lighthouse, axe, browser E2E |
| FR-UI-003 | Upload/KB screens | document/collection/job endpoints | `test_req_fr_ui_003_upload_e2e` | upload/job completion and error rates |
| FR-UI-004 | Role-gated admin/settings, sanitizer | admin API and UI | `test_req_fr_ui_004_roles_xss` | authorization failures, XSS gate |
| FR-STA-001 | Health/readiness and metrics middleware; private worker metrics listener | `/healthz`, `/readyz`, protected `/metrics`; worker `:9000/metrics` on backend network | `test_healthz_reports_liveness_without_dependencies`; `test_readyz_reports_missing_dependencies_as_not_ready`; `test_metrics_route_requires_bearer_secret` | HTTP/query/job outcomes and durations; local Alloy scrape configured |
| FR-STA-002 | Request middleware, OTel spans, redacted structured security events, bounded LangSmith exporter | all requests/jobs | `test_req_fr_sta_002_redaction_correlation`; `test_telemetry_redaction_masks_pii_and_credential_patterns_recursively`; security smoke suite | `rag_tracing_export_failures_total`, trace/request correlation; job trace IDs and cloud freshness alerts remain open |

## Non-functional verification map

| NFR | Architectural decisions/components | Verification and planned evidence | Monitoring/SLO |
|---|---|---|---|
| NFR-PERF-001/002 | ADR-001, 003, 008, 013, 014; bounded retrieval candidates, context, output tokens and provider timeout | pinned model staging load test, `EXPLAIN ANALYZE`; pending | p95 TTFT/full answer/non-LLM latency; TTFT risk documented in ADR-014 |
| NFR-SCALE-001/002 | ADR-001, 004, 006, 013; horizontally scaled API/workers with upload/page/chunk/queue/concurrency bounds | concurrent capacity/soak test, 100-page synthetic PDF | saturation, queue age, memory, throughput |
| NFR-AVAIL-001 | ADR-002, 004, 010, 013; bounded queue failure maps to retryable 503 and readiness includes queue | monthly synthetic SLI and deployment checks | 99.5% proposed API availability |
| NFR-REL-001 | ADR-004, 006, 008, 013-015; stable job IDs, idempotent ingestion/deletion, tenant epoch cache invalidation, fail-open cache, circuit breakers, capped jittered retries | dependency fault injection, duplicate delivery and breaker tests | 5xx, worker retry/dead-letter counters; breaker state and provider error metrics remain open |
| NFR-DR-001 | ADR-001, 004, 005, 010 | scheduled restore drill with measured RTO/RPO | backup status, restore drill evidence |
| NFR-SEC-001/002/003 | ADR-007, 008, 011-015; tenant RLS, quarantine/review, no-tool prompt boundary, PII/output/canary scans | CI RLS smoke, `make redteam`, gitleaks, TLS and secret tests | `rag_ai_security_events_total`, immediate canary metric alert; smoke tests do not prove zero production attack success |
| NFR-PRIV-001 | ADR-005, 011, 013; private source storage, metadata redaction on deletion, bounded log fields | export payload and retention/deletion review | purge lag, trace export data audit |
| NFR-AI-001/002 | ADR-003, 008, 009, 013, 014; eligible chunk filters, evidence refusal, strict citation membership | M6 golden set and adversarial/browser tests; M4 unit tests cover citation mismatch | retrieval/groundedness/citation/refusal trends pending telemetry |
| NFR-A11Y-001, UX-001 | ADR-009 | axe, Lighthouse, keyboard/SR and i18n E2E | accessibility score and issue count |
| NFR-MAINT-001, TEST-001 | hexagonal layering, ingestion ports/adapters, CI contract, 80% unit coverage gate; ADR-013 | coverage, mypy, Ruff, import-linter, traceability CI | M3: 81% coverage, strict mypy, Ruff and import-linter pass; live provider contract tests remain planned |
| NFR-OBS-001 | ADR-011/015/017, OTel middleware, Prometheus API/worker endpoints, bounded LangSmith adapter, Alloy/Grafana profile | telemetry/redaction unit tests, local profile check, staging alert exercise pending | request/query/job terminal metrics; stage timing/feedback and cloud missing-telemetry alerts remain open |
| NFR-PORT-001 | ADR-001, 005, 006, 008, 011, 012 | local Compose has separate Redis state/cache policies; shared adapter contract suites/local composition | adapter conformance report |
| NFR-COMP-001 | ADR-009 | Playwright current/previous browser matrix | browser E2E pass rate |
| NFR-COST-001 | ADR-008, 006 | provider reconciliation, spend-cap/kill-switch exercise | cost/query, spend/tenant, budget alert |
| NFR-OPS-001 | ADR-004, 010, 012, 013, 014 | async lifecycle cleanup, bounded work, provider timeouts/circuit breakers, readiness and migration/runtime role separation; later SIGTERM/deploy checks | local migration and role smoke, unit tests; staging deploy/rollback not yet run | request metrics and readiness live; deployment health/rollback metrics planned |
| NFR-DATA-001 | ADR-001, 004, 005, 006, 011, 013 | partial-write/crash tests and deletion/restore drills | deletion completion, recovery objectives |

## Milestone 7 infrastructure traceability

| Requirement/NFR | Component | Endpoint/resource | Verification | Monitoring/SLO |
|---|---|---|---|---|
| FR-STA-001 | `infra/terraform/main.tf`: Render API web service and readiness gate | Render API `/readyz`; protected API `/metrics` | Terraform fmt/validate and provider schema check passed; staging health probe pending | API readiness and availability SLI pending staging |
| FR-STA-002, NFR-OBS-001 | Alloy private service and `infra/alloy/config.alloy` | API/Postgres/Redis scrape targets, OTLP HTTP `:4318`, Grafana Cloud remote write/OTLP | Alloy config validated against pinned v1.22.0 image; end-to-end cloud smoke pending; worker metrics and app stdout log export are known gaps | Dashboard and three alert rules are configured; alert delivery exercise pending |
| NFR-REL-001, NFR-DR-001 | Separate Render Redis resources; Render Postgres | state/cache Redis internal URLs; Postgres internal URL | Provider schema validates; apply, Redis outage test, backup/restore drill pending | Redis memory/eviction and Postgres backup signals pending staging |
| NFR-SEC-003 | Sensitive Terraform variables, Render env group, remote backend, isolated environments | GitHub protected staging environment and HCP workspace | Static secret scan/Checkov and live access review pending | No secret values in public CI output; state access audit pending |
| NFR-OPS-001 | Terraform 1.17.2, exact-pinned providers, `/readyz` gate, CI-only apply | `make tf-plan`; protected staging workflow | `terraform fmt` and `terraform validate` run; staging plan/deploy/smoke/rollback pending owner inputs | Deploy status and readiness checks pending |

