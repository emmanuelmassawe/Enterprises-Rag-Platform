# Requirements traceability

Status: design-time map. Test names below are proposed verification IDs; no tests exist or were run in Phase 0. Implementation must add tests referencing each FR and CI must fail on missing/unknown IDs. Monitoring columns are planned signals, not currently deployed instruments.

## Functional requirements

| Requirement | Component | Endpoint(s) | Planned test ID(s) | Monitoring / SLO |
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
| FR-AUTH-001 | API-key auth, key repository | `/v1/admin/api-keys*`; all protected routes | `test_req_fr_auth_001_key_scope_revocation` | auth failures, key revocations (bounded labels) |
| FR-AUTH-002 | Google OIDC, BFF, session store | BFF login/logout and API proxy | `test_req_fr_auth_002_session` | login failures, session errors; no identity labels |
| FR-AUTH-003 | Policy/tenant context, RLS, DB roles | all tenant endpoints | `test_req_fr_auth_003_rls_isolation` | cross-tenant attempt security event; target zero leaks |
| FR-AUTH-004 | RateLimiter, QuotaStore, concurrency guard | query/upload/write endpoints | `test_req_fr_auth_004_quota` | 429 count, quota consumption, cost anomaly |
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
| FR-STA-001 | Health/readiness and metrics middleware | `/healthz`, `/readyz`, `/metrics`, `/v1/admin/status` | `test_req_fr_sta_001_health_metrics` | uptime/readiness, scrape freshness |
| FR-STA-002 | Logging/OTel/redaction middleware | all requests/jobs | `test_req_fr_sta_002_redaction_correlation` | trace completeness/export failure |

## Non-functional verification map

| NFR | Architectural decisions/components | Verification and planned evidence | Monitoring/SLO |
|---|---|---|---|
| NFR-PERF-001/002 | ADR-001, 003, 008; route/pipeline histograms | pinned model staging load test, `EXPLAIN ANALYZE` | p95 TTFT/full answer/non-LLM latency |
| NFR-SCALE-001/002 | ADR-001, 004, 006; horizontally scaled API/workers | concurrent capacity/soak test, 100-page synthetic PDF | saturation, queue age, memory, throughput |
| NFR-AVAIL-001 | ADR-002, 004, 010 | monthly synthetic SLI and deployment checks | 99.5% proposed API availability |
| NFR-REL-001 | ADR-004, 006, 008 | dependency fault injection and duplicate delivery | 5xx, retries, breaker state |
| NFR-DR-001 | ADR-001, 004, 005, 010 | scheduled restore drill with measured RTO/RPO | backup status, restore drill evidence |
| NFR-SEC-001/002/003 | ADR-007, 008, 009, 011 | RLS suite, red-team, gitleaks, TLS and secret tests | zero leakage target, security event counts |
| NFR-PRIV-001 | ADR-005, 011 | export payload and retention/deletion review | purge lag, trace export data audit |
| NFR-AI-001/002 | ADR-003, 008, 009 | golden set and adversarial/browser tests | retrieval/groundedness/citation/refusal trends |
| NFR-A11Y-001, UX-001 | ADR-009 | axe, Lighthouse, keyboard/SR and i18n E2E | accessibility score and issue count |
| NFR-MAINT-001, TEST-001 | hexagonal layering, CI contract | coverage, mypy, Ruff, import-linter, traceability CI | CI status; zero untraced FRs |
| NFR-OBS-001 | ADR-011 | telemetry/redaction tests and alert exercise | trace completeness, missing telemetry alerts |
| NFR-PORT-001 | ADR-001, 005, 008, 011 | shared adapter contract suites/local composition | adapter conformance report |
| NFR-COMP-001 | ADR-009 | Playwright current/previous browser matrix | browser E2E pass rate |
| NFR-COST-001 | ADR-008, 006 | provider reconciliation, spend-cap/kill-switch exercise | cost/query, spend/tenant, budget alert |
| NFR-OPS-001 | ADR-004, 010 | SIGTERM, health-gated staging deploy/rollback | deploy health, restart/rollback metrics |
| NFR-DATA-001 | ADR-001, 004, 005, 006, 011 | partial-write/crash tests and deletion/restore drills | deletion completion, recovery objectives |

