# Requirements traceability

Status: mixed. Milestone 2 authentication, rate limiting, persistence foundations and operational checks have implementation and test evidence; later milestone rows remain planned. CI must keep all FR references and tests synchronized. Monitoring columns distinguish live signals from planned signals.

## Functional requirements

| Requirement | Component | Endpoint(s) | Test ID(s) | Monitoring / SLO |
|---|---|---|---|---|
| FR-ING-001 | Upload API, BlobStore, parser | POST `/v1/documents` | `test_req_fr_ing_001_upload_validation` | upload rejects, bytes, unsupported MIME counter |
| FR-ING-002 | Worker, job service, queue | POST `/v1/documents`; GET `/v1/jobs/{id}`; POST `/v1/jobs/{id}/retry`; DELETE job | `test_req_fr_ing_002_job_state` | queue depth, oldest age, duration, failures, DLQ |
| FR-ING-003 | Content scanner, quarantine service | document job; `/v1/admin/quarantine*` | `test_req_fr_ing_003_quarantine` | quarantined chunks, detector rate, review age |
| FR-ING-004 | Parser/provenance, citation DTO | POST documents; GET documents; POST query | `test_req_fr_ing_004_provenance` | missing page metadata, citation resolution failure |
| FR-ING-005 | Deletion orchestrator, BlobStore, Redis, telemetry lifecycle | DELETE document/collection | `test_req_fr_ing_005_delete_cascade` | deletion backlog/partial failures |
| FR-QRY-001 | Query service, ACL retrieval, RLS, hybrid search | POST `/v1/query` | `test_req_fr_qry_001_scope` | retrieval latency, empty-result rate |
| FR-QRY-002 | Evidence threshold, refusal policy | POST `/v1/query` | `test_req_fr_qry_002_refusal` | refusal rate, refusal accuracy eval |
| FR-QRY-003 | SSE transport, provider cancellation | POST `/v1/query` | `test_req_fr_qry_003_sse_terminal_cancel` | TTFT, stream duration, cancellations |
| FR-CIT-001 | Citation verifier, output validator | POST `/v1/query` | `test_req_fr_cit_001_citation_membership` | citation validation failures/accuracy |
| FR-CIT-002 | Prompt builder, output scanner, safe UI renderer | POST `/v1/query`; UI | `test_req_fr_cit_002_untrusted_output` | blocked output, injection events; XSS gate |
| FR-QRY-004 | Cache adapter, circuit breaker, fallback policy | POST `/v1/query` | `test_req_fr_qry_004_cache_failure` | cache hit ratio, provider errors, fallback count |
| FR-CNV-001 | Conversation service, RLS | `/v1/conversations*` | `test_req_fr_cnv_001_ownership` | authz failures, conversation CRUD errors |
| FR-CNV-002 | Message repository, retention | GET messages; DELETE conversation | `test_req_fr_cnv_002_pagination_retention` | message page latency, retention/deletion lag |
| FR-AUTH-001 | API-key auth service, Postgres key repository, bootstrap CLI | `/v1/admin/api-keys*`; all protected routes | `test_req_fr_auth_001_api_key_is_hashed_and_returned_once`; `test_req_fr_auth_001_invalid_and_insufficient_credentials_are_denied`; `test_req_fr_auth_001_revoke_and_expiry_invalidate_credentials`; `test_req_fr_auth_001_postgres_store_*` | API request status counts; key secrets never logged; auth failure dashboards remain planned |
| FR-AUTH-002 | Google OIDC, BFF, session store | BFF login/logout and API proxy | `test_req_fr_auth_002_session` | login failures, session errors; no identity labels |
| FR-AUTH-003 | Transaction-local DB tenant context, forced Postgres RLS, separate migration/runtime roles | tenant-scoped repositories | `test_req_fr_auth_003_database_sets_transaction_local_identity`; CI migration/RLS smoke with two synthetic tenants | CI verifies tenant visibility and cross-tenant insert denial; security event aggregation remains planned |
| FR-AUTH-004 | Redis fixed-window `RateLimiter`, bounded local fallback | `/v1/admin/api-keys*`; future protected query/upload/write endpoints | `test_req_fr_auth_004_memory_limiter_*`; `test_req_fr_auth_004_shared_limiter_uses_atomic_tenant_key_counter`; `test_req_fr_auth_004_limiter_uses_fallback_when_no_redis_is_configured` | Live `rag_rate_limit_fallback_total`; 429 status counts; quotas/cost anomaly remain planned |
| FR-KB-001 | Collection/document use cases and repositories | `/v1/collections*`; `/v1/documents` | `test_req_fr_kb_001_crud_scope` | CRUD errors, delete cascade age |
| FR-ADM-001 | Quarantine review/audit service | `/v1/admin/quarantine*` | `test_req_fr_adm_001_review_audit` | review queue depth/age, decisions |
| FR-ADM-002 | Usage aggregation, API key service, status | `/v1/admin/usage`; `/v1/admin/api-keys*`; `/v1/admin/status` | `test_req_fr_adm_002_admin_scope` | usage/cost, admin endpoint errors |
| FR-FBK-001 | Feedback service, query correlation, LangSmith adapter | POST `/v1/feedback` | `test_req_fr_fbk_001_feedback` | feedback rate, export failure counter |
| FR-EVL-001 | Eval harness, version registry | offline `make eval`; no runtime endpoint | `test_req_fr_evl_001_golden_eval` | recall@k, groundedness, citation/refusal metrics |
| FR-USG-001 | Usage ledger, provider wrapper, quota service | POST query; GET admin usage | `test_req_fr_usg_001_accounting` | token/cost estimate, tenant quota events |
| FR-UI-001 | Web chat and citation renderer | query, feedback, conversation/messages | `test_req_fr_ui_001_chat_e2e` | Faro route/error/web vital; query SLO |
| FR-UI-002 | i18n/theme/responsive/a11y system | UI routes | `test_req_fr_ui_002_locale_a11y` | Lighthouse, axe, browser E2E |
| FR-UI-003 | Upload/KB screens | document/collection/job endpoints | `test_req_fr_ui_003_upload_e2e` | upload/job completion and error rates |
| FR-UI-004 | Role-gated admin/settings, sanitizer | admin API and UI | `test_req_fr_ui_004_roles_xss` | authorization failures, XSS gate |
| FR-STA-001 | Health/readiness and metrics middleware | `/healthz`, `/readyz`, protected `/metrics` | `test_healthz_reports_liveness_without_dependencies`; `test_readyz_reports_missing_dependencies_as_not_ready`; `test_metrics_route_requires_bearer_secret` | request counters/histograms; uptime and scrape freshness planned |
| FR-STA-002 | Logging/OTel/redaction middleware | all requests/jobs | `test_req_fr_sta_002_redaction_correlation` | trace completeness/export failure |

## Non-functional verification map

| NFR | Architectural decisions/components | Verification and planned evidence | Monitoring/SLO |
|---|---|---|---|
| NFR-PERF-001/002 | ADR-001, 003, 008; route/pipeline histograms | pinned model staging load test, `EXPLAIN ANALYZE` | p95 TTFT/full answer/non-LLM latency |
| NFR-SCALE-001/002 | ADR-001, 004, 006; horizontally scaled API/workers | concurrent capacity/soak test, 100-page synthetic PDF | saturation, queue age, memory, throughput |
| NFR-AVAIL-001 | ADR-002, 004, 010 | monthly synthetic SLI and deployment checks | 99.5% proposed API availability |
| NFR-REL-001 | ADR-004, 006, 008 | dependency fault injection and duplicate delivery | 5xx, retries, breaker state |
| NFR-DR-001 | ADR-001, 004, 005, 010 | scheduled restore drill with measured RTO/RPO | backup status, restore drill evidence |
| NFR-SEC-001/002/003 | ADR-007, 009, 011, 012 | CI RLS smoke, later red-team, gitleaks, TLS and secret tests | RLS visibility and denied insert verified; zero leakage target and security event counts remain monitored release goals |
| NFR-PRIV-001 | ADR-005, 011 | export payload and retention/deletion review | purge lag, trace export data audit |
| NFR-AI-001/002 | ADR-003, 008, 009 | golden set and adversarial/browser tests | retrieval/groundedness/citation/refusal trends |
| NFR-A11Y-001, UX-001 | ADR-009 | axe, Lighthouse, keyboard/SR and i18n E2E | accessibility score and issue count |
| NFR-MAINT-001, TEST-001 | hexagonal layering, CI contract, 80% unit coverage gate | coverage, mypy, Ruff, import-linter, traceability CI | Local M2 static checks and 86% coverage passed; full adapter contract inventory remains planned |
| NFR-OBS-001 | ADR-011 | telemetry/redaction tests and alert exercise | trace completeness, missing telemetry alerts |
| NFR-PORT-001 | ADR-001, 005, 008, 011 | shared adapter contract suites/local composition | adapter conformance report |
| NFR-COMP-001 | ADR-009 | Playwright current/previous browser matrix | browser E2E pass rate |
| NFR-COST-001 | ADR-008, 006 | provider reconciliation, spend-cap/kill-switch exercise | cost/query, spend/tenant, budget alert |
| NFR-OPS-001 | ADR-004, 010, 012 | async lifecycle cleanup, readiness and migration/runtime role separation; later SIGTERM/deploy checks | local migration and role smoke, unit tests; staging deploy/rollback not yet run | request metrics and readiness live; deployment health/rollback metrics planned |
| NFR-DATA-001 | ADR-001, 004, 005, 006, 011 | partial-write/crash tests and deletion/restore drills | deletion completion, recovery objectives |

