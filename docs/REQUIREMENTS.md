# Requirements

Status: Phase 0 proposal, pending owner approval. This document does not authorize implementation.

## Purpose and scope

Define an authenticated, multi-tenant document question-answering service for internal knowledge. V1 ingests PDF files, indexes them, and answers questions with evidence and citations through an API and English/Swahili web interface. See [Glossary](GLOSSARY.md). Scope is based on [BRIEF.md](BRIEF.md) and [OWNER_DECISIONS.md](OWNER_DECISIONS.md).

## Stakeholders and personas

- **Knowledge user (viewer):** asks questions and inspects cited source passages.
- **Knowledge editor:** maintains collections, uploads and deletes documents, follows ingestion.
- **Tenant administrator:** manages people/API keys, reviews quarantine and usage, and sees system status for their tenant.
- **Platform operator:** operates services, quotas, evaluation, security and incident response across tenants.
- **Owner:** approves requirements, target budgets, providers, retention and release gates.

## Assumptions and constraints

- Owner decisions: about 20 users at 12 months; English documents; PDF only, at least 20 pages; Gemini API for generation and Gemini embeddings; documents are not sensitive but privacy is required; EU/US processing is acceptable; Google-only web login; `localhost` development address.
- Those facts do not settle page-size maximum, tenant count, model/version/dimension, authentication protocol, retention, spend, hosting region or production domain.
- BRIEF defaults: Python 3.12/FastAPI, Postgres + pgvector and FTS, Redis-compatible Render Key Value, provider ports, Render/Terraform, LangSmith, Grafana Cloud, REST + SSE, Next.js BFF.
- Public repository: all committed material must be synthetic and free of credentials, customer data and production identifiers.
- Unless a decision is explicitly in OWNER_DECISIONS.md, quantitative values below are **proposed, confirm with owner**. Some are gates to be set after baseline rather than guessed.

## Out of scope for v1

Fine-tuning, multi-region deployment, agent tools/actions, public sharing, non-PDF document ingestion, and automatic self-service account registration unless later approved.

## Functional requirements

Each criterion is normative after owner approval. Priority uses MoSCoW.

### Ingestion (FR-ING)

| ID | Requirement / Priority | Given / When / Then acceptance criteria |
|---|---|---|
| FR-ING-001 | The system shall accept PDF uploads only, with a configurable bounded size and verified PDF content. **Must** | Given an authorized editor and a valid PDF within configured limits, when uploaded with an idempotency key, then return 202 and document/job identifiers; Given a mislabeled, malformed, oversized or unsupported file, when uploaded, then reject it with a stable problem code and create no retrievable content. |
| FR-ING-002 | The system shall process ingestion asynchronously and expose per-document job progress and safe errors. **Must** | Given an accepted upload, when processing advances, then the job transitions queued→processing→ready or failed and polling returns state/progress; Given a retryable failure, when retried, then duplicate delivery does not duplicate indexed chunks. |
| FR-ING-003 | The system shall scan and quarantine suspicious document chunks before retrieval. **Must** | Given a chunk flagged by the configured injection/content scanner, when indexing completes, then it is quarantined and absent from normal retrieval; Given an admin decision, when approved/rejected, then the decision is audited and applies only to the authorized tenant. |
| FR-ING-004 | The system shall retain source provenance and stable page/section metadata for citations. **Must** | Given a parsable PDF, when indexed, then each chunk preserves source document and page metadata; Given a citation, when displayed, then its cited passage resolves to that document/page or an explicit unavailable-source error. |
| FR-ING-005 | The system shall delete a document and its derived data through an auditable cascade. **Must** | Given an authorized delete, when completed, then raw object, chunks, embeddings, related cache entries and eligible derived logs are purged or queued for purge with a visible completion status; repeated delete is safe. |

### Query, answer and grounding (FR-QRY, FR-CIT)

| ID | Requirement / Priority | Given / When / Then acceptance criteria |
|---|---|---|
| FR-QRY-001 | The system shall retrieve only accessible evidence from the selected tenant collections and answer through a bounded, configurable pipeline. **Must** | Given a scoped question, when queried, then candidate retrieval respects collection/document ACLs and configured top-k/context/token limits; no other tenant's content is used. |
| FR-QRY-002 | The system shall refuse when evidence is absent or below an approved threshold. **Must** | Given no qualifying evidence, when queried, then return a typed refusal without unsupported factual claims and a user-readable next step. |
| FR-QRY-003 | The system shall stream answers over the versioned SSE contract and support cancellation. **Must** | Given a stream request, when generation runs, then events follow the documented sequence, end with exactly one `done` or `error`, and cancellation stops upstream work within the configured timeout. |
| FR-CIT-001 | The system shall verify citations against retrieved chunk IDs and source metadata. **Must** | Given generated claims, when output validation runs, then only citations to chunks in that request's retrieved set are emitted; invalid references cause repair/refusal, not fabricated citations. |
| FR-CIT-002 | The system shall treat retrieved text and model output as untrusted. **Must** | Given adversarial retrieved or generated text, when prompt assembly/rendering occurs, then context is delimited, output schema-validated and unsafe HTML/images/auto-fetch links are not executed or loaded. |
| FR-QRY-004 | The system shall provide tenant-scoped, versioned cache and explicit degradation behavior. **Must** | Given cache/provider failure, when a query runs, then cache may fail open, provider failure returns a safe retryable error or configured retrieval-only result, and no stale/ineligible citation is served. |

### Conversations (FR-CNV)

| ID | Requirement / Priority | Given / When / Then acceptance criteria |
|---|---|---|
| FR-CNV-001 | The system shall create, list, rename, and delete user/tenant-scoped conversations. **Must** | Given an authenticated user, when conversation CRUD is performed, then only that user's authorized tenant records are returned or changed; cross-tenant/unauthorized IDs return a non-disclosing error. |
| FR-CNV-002 | The system shall persist and paginate conversation messages under configured retention. **Must** | Given a conversation, when messages are listed, then cursor pagination is stable and message content is returned only to authorized participants; deletion/retention cascades apply. |

### Tenancy, authentication and authorization (FR-AUTH)

| ID | Requirement / Priority | Given / When / Then acceptance criteria |
|---|---|---|
| FR-AUTH-001 | The system shall authenticate machine API clients with hashed, revocable, scoped API keys. **Must** | Given a valid key, when a scoped operation is requested, then its tenant and scopes are resolved server-side; invalid, expired, revoked or insufficient-scope keys receive stable 401/403 errors. |
| FR-AUTH-002 | The web UI shall authenticate through Google login and a same-origin BFF session. **Must** | Given a valid Google identity mapped to an active tenant, when login completes, then browser receives only a secure HttpOnly session cookie and no provider/API secret; logout invalidates session and clears client state. |
| FR-AUTH-003 | The system shall authorize viewer/editor/admin roles and enforce tenant isolation in PostgreSQL RLS as well as application filters. **Must** | Given any user or service identity, when queries execute, then tenant context is bound transaction-locally and RLS blocks cross-tenant reads/writes even if an app filter is omitted. |
| FR-AUTH-004 | The system shall apply bounded per-key and per-tenant rate, concurrency and spend quotas. **Must** | Given a limit is reached, when another operation is attempted, then return 429 with Retry-After/quota headers and emit a tenant-safe security/usage event. |

### Knowledge base and admin (FR-KB, FR-ADM)

| ID | Requirement / Priority | Given / When / Then acceptance criteria |
|---|---|---|
| FR-KB-001 | The system shall support tenant-scoped collection create/list/rename/delete and document list/search/filter operations. **Must** | Given an authorized editor, when collection/document operations are requested, then only tenant-scoped resources are changed; deletes apply configured cascade rules and are auditable. |
| FR-ADM-001 | The system shall provide an admin review queue for quarantined content, displayed as plain text. **Must** | Given a tenant admin and quarantined item, when reviewed and approved/rejected, then action, actor, timestamp and reason are audited; other tenants' items remain invisible. |
| FR-ADM-002 | The system shall expose tenant usage/cost summaries and key lifecycle operations to authorized admins. **Must** | Given an admin request for a bounded date range, when summaries are returned, then totals are tenant-filtered, paginated where needed, and distinguish estimates from provider-reported cost. |

### Feedback, evaluation and usage (FR-FBK, FR-EVL, FR-USG)

| ID | Requirement / Priority | Given / When / Then acceptance criteria |
|---|---|---|
| FR-FBK-001 | The system shall accept answer feedback with optional reason, correlated to a query/run without requiring message content in telemetry. **Must** | Given an authorized user and answer, when feedback is submitted, then it is stored against the correct tenant/query and duplicate submission behavior is deterministic. |
| FR-EVL-001 | The system shall run retrieval and answer evaluation on a synthetic or licensed golden set with versioned results. **Must** | Given a pinned dataset/model/pipeline version, when evaluation runs, then output recall@k, MRR/nDCG, groundedness, citation accuracy and refusal accuracy; regression gates use owner-approved thresholds. |
| FR-USG-001 | The system shall account for per-request tokens, cost estimate, tenant usage and quota events. **Must** | Given completed or failed provider work, when usage is recorded, then counters are idempotent, tenant-scoped, labeled with model/version and export no raw query text. |

### Web UI, status and notifications (FR-UI, FR-STA)

| ID | Requirement / Priority | Given / When / Then acceptance criteria |
|---|---|---|
| FR-UI-001 | The UI shall provide chat with streaming, citations, refusal, retry/cancel, feedback, history and collection scope. **Must** | Given a signed-in user, when asking a question, then the UI shows retrieving/streaming/complete/refused/error states, verified citation source panel and usable cancel/retry controls. |
| FR-UI-002 | The UI shall support English and Swahili, light/dark/system themes, responsive layouts and keyboard/screen-reader use. **Must** | Given either locale, theme or supported viewport, when core flows are used, then strings/layout remain usable and controls have labels, focus and polite status announcements. |
| FR-UI-003 | The UI shall manage uploads, jobs, documents and collections with safe delete confirmation and visible per-file progress. **Must** | Given an editor, when files are uploaded or managed, then local validation mirrors server limits and authoritative job status/errors are displayed. |
| FR-UI-004 | The UI shall provide role-gated settings and admin views without exposing internal retrieval scores to non-admins. **Must** | Given a viewer/editor/admin, when navigating, then only authorized actions/data are exposed and model output is sanitized without HTML execution or remote image loading. |
| FR-STA-001 | The service shall expose liveness, readiness and internal metrics/status signals. **Must** | Given dependencies are healthy/unhealthy, when health endpoints are probed, then liveness reports process status, readiness reflects required dependencies, and metrics are not publicly exposed. |
| FR-STA-002 | The system shall emit actionable, redacted structured events and traces with correlation IDs. **Must** | Given a request/job/security event, when observed, then request/trace correlation is available without raw secrets, PII, questions or document text in external telemetry. |

## Non-functional requirements

All numeric starting targets marked below are **proposed, confirm with owner**. Verification methods specify future evidence; no implementation or runtime measurements are claimed in Phase 0.

| ID | Category | Measurable target | Measurement and verification |
|---|---|---|---|
| NFR-PERF-001 | Query latency | **Proposed:** p95 time-to-first-token ≤3 s; p95 full answer ≤10 s for typical queries, excluding provider outages. | OTel histograms by pipeline step; staging load test with fixed query mix and pinned provider/model. |
| NFR-PERF-002 | API latency | **Proposed:** p95 non-LLM API ≤300 ms at agreed baseline load. | Route histograms; k6/Locust load test. |
| NFR-SCALE-001 | Capacity | **Proposed:** 100 concurrent chat streams, 10 tenants, 1M chunks; state owner-provided ~20 users at 12 months separately. | Staging capacity and soak test; record throughput, p95/p99, saturation and memory. Scale horizontally for API/workers; partition/index/re-evaluate retrieval beyond target. |
| NFR-SCALE-002 | Ingestion | **Proposed:** 100-page PDF processed within 2 min under stated baseline: paid staging plans, text-based PDF, bounded file size, provider operational. Owner decision says PDF 20 pages+; max pages/size open. | Synthetic PDFs; measure queue wait and processing duration, repeat at concurrency. |
| NFR-AVAIL-001 | Availability | **Proposed:** API monthly availability ≥99.5%, staging excluded. | SLI from synthetic checks and request success; monthly SLO dashboard and incident review. |
| NFR-REL-001 | Reliability | **Proposed:** 5xx ≤0.5% monthly, excluding caller errors; retry only idempotent calls with bounded backoff/jitter. | Error-rate metrics, fault-injection tests for each dependency and duplicate jobs. |
| NFR-DR-001 | Recovery | **Proposed:** RPO ≤24 h; RTO ≤4 h. | Scheduled Postgres restore drill and measured recovery; validate object-store backup/lifecycle and Redis state recovery assumptions. |
| NFR-SEC-001 | Isolation | Zero cross-tenant disclosure in the RLS adversarial suite. | Integration tests using separate roles/tenants and deliberate missing-filter cases; security events. |
| NFR-SEC-002 | Security response | **Proposed:** red-team attack success rate 0% for cross-tenant, secret/prompt exfiltration, executable XSS/image payload classes; ≤5% for other defined classes before owner review. | CI smoke per PR and nightly full attack suite; report per category, do not treat ASR as proof of safety. |
| NFR-SEC-003 | Secrets and transport | 100% external service traffic TLS; no secret in repository/history/telemetry; provider and DB keys scoped per environment. | Gitleaks/push protection, TLS config review, secret scan and log redaction tests. |
| NFR-PRIV-001 | Privacy/retention | No raw prompts, document text, or direct user identifiers exported to LangSmith/Grafana; retention period configurable and deletion cascade completion measurable. | Export payload tests, retention/deletion integration tests and quarterly privacy review. Retention duration pending owner. |
| NFR-AI-001 | Grounding | Baseline first; thereafter owner-approved thresholds for recall@k, groundedness, citation accuracy and refusal accuracy; no threshold is claimed before baseline. | Versioned golden set and evaluation report; thresholds approved after baseline run. |
| NFR-AI-002 | Safe output | 100% invalid citation IDs rejected; 0 executable scripts or auto-loaded model-generated images/links in UI adversarial tests. | Schema/citation property tests and browser XSS tests. |
| NFR-A11Y-001 | Accessibility | WCAG 2.2 AA for key flows; Lighthouse accessibility ≥90 proposed. | axe in CI, keyboard and screen-reader review, Lighthouse CI on key pages. |
| NFR-UX-001 | Usability/i18n | All user-facing UI strings localized EN/SW; core flows complete without pointer; supported viewport from 360 px width. | Locale completeness check, Playwright flows, mobile viewport and moderated usability review. |
| NFR-MAINT-001 | Maintainability | Line coverage ≥80%; zero import-linter violations; mypy strict and Ruff clean; cyclomatic complexity ≤10 per function except documented exception. | CI reports and static checks; coverage excludes generated code only by documented rule. |
| NFR-TEST-001 | Testability | Every FR maps to at least one behavior/contract test; every port has shared contract suite for real and fake adapters. | CI traceability check and contract-test inventory. |
| NFR-OBS-001 | Observability | 100% API/job requests have request/trace IDs and terminal outcome metric; alerts have runbook; no high-cardinality query/user/document labels. | Telemetry integration tests, metrics schema review, alert exercise in staging. |
| NFR-PORT-001 | Portability | Provider changes are isolated behind ports; local docker-compose supports Postgres/pgvector, two Redis semantics, blob emulator and observability profile. | Adapter contract suites and local setup/runbook review. |
| NFR-COMP-001 | Compatibility | Latest and previous major Chrome, Edge, Firefox, Safari; responsive iOS Safari and Android Chrome (proposed matrix). | Playwright browser matrix and manual device smoke test. |
| NFR-COST-001 | Cost | Maximum LLM+embedding cost/query and tenant/month and infrastructure budget per environment are owner-set; no numeric cap approved yet. Per-tenant hard quotas and provider spend cap required before production. | Provider usage reconciliation, usage dashboard, budget alert and kill-switch exercise. |
| NFR-OPS-001 | Operability | API and worker graceful shutdown ≤30 s proposed; deploy health gate, rollback and smoke procedure; no production Terraform apply outside approved CI. | SIGTERM integration check, staging deployment/rollback rehearsal, CI policy review. |
| NFR-DATA-001 | Data durability | All writes acknowledged only after durable source/metadata and recoverable job state; deletion cascade covers DB, blobs, Redis, logs/traces per retention. | Crash/duplicate/partial-write fault tests and restore drill. |

## Open questions for owner

1. What is the product use case and consequence class (general company knowledge, support, regulated/high-impact)?
2. How many tenants at launch and in 12 months? Does the ~20 user estimate mean total or per tenant?
3. Confirm PDF-only scope, minimum 20 pages, maximum pages/bytes, scanned-PDF OCR requirement, and launch document volume.
4. Confirm Gemini model IDs/versions for generation and embeddings, embedding dimensions, region/endpoint, provider data retention/training terms, and whether Gemini is compatible with the chosen LangSmith tracing integration.
5. Confirm expected account flow: Google Workspace domain allowlist, OIDC identity provider, tenant/user provisioning and account removal.
6. Choose Render region, paid service plans, production domain (localhost is suitable only for local development), and staging/production budget.
7. Set API and tenant count, rate/token/concurrency quotas, maximum query and monthly AI spend, plus per-environment infrastructure budget.
8. Choose document, conversation, query-log, security-event, and LangSmith retention periods; define deletion legal hold behavior and privacy jurisdiction.
9. Name operational owner/on-call, escalation channel, support hours and incident notification obligations.
10. Approve targets or changes for availability, latency, capacity, RPO/RTO, accessibility, browser matrix, red-team thresholds and post-baseline RAG quality gates.
11. Confirm license (public repository currently has no license decision), data residency and any contractual/DPA requirements.
12. Confirm whether read-only sharing, notifications/webhooks, user feedback reasons and tenant admins managing keys are desired in v1.

