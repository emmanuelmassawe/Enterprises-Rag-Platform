# Task: Build a Production-Grade RAG System (deployed on Render via Terraform)

You are a senior staff engineer. Build a production-grade Retrieval-Augmented Generation (RAG) service from scratch in this repository. Follow proper system-design and engineering practices. Do not build a demo or notebook: build a maintainable, tested, observable, deployable service.

## 0. How to work (read first)

1. **Plan before coding.** Start by writing `docs/ARCHITECTURE.md` (components, data flow diagram in Mermaid, trade-offs) and `docs/ADR/` entries for each major decision. Do NOT write application code until Phase 0 (Section 0A: requirements, API design, architecture) is complete and the human owner has approved it. Keep these documents updated afterwards.
2. Work in small, reviewable milestones (see section 12). After each milestone: run lint, type-check and tests, then commit with a Conventional Commit message.
3. Never hardcode secrets. Never commit `.env` or `terraform.tfstate`.
4. If a requirement is ambiguous, choose the simplest production-sound default, document it in an ADR, and continue.
5. Verify Render Terraform provider resource names and arguments against the official provider docs (`render-oss/render` on the Terraform Registry) before writing `.tf` files. Do not guess arguments. If the provider cannot express something, document the gap and provide a documented manual/API fallback.
6. Apply Section 2B (software engineering principles) and Section 2A (AI design principles) to every change. Architecture rules are enforced by tooling (import-linter, mypy strict, ruff), not just by convention.
7. All code must meet the Production-Readiness Standard (Section 10B) from the first commit: no placeholders or stubs in production paths, real implementations, tested failure modes. Do not defer hardening to the end.

## 0A. Phase 0: Design-First (NO application code until approved)

Before writing any application code (no `src/`, `web/` or business logic; repo scaffolding is also postponed to Milestone 1), complete and commit the design deliverables below, then **STOP and ask the human owner to review and approve them**. Do not proceed to Milestone 1 until approval is given in writing. Changes to approved requirements or the API contract later require an ADR and an updated document (change control).

### Deliverable 1: `docs/REQUIREMENTS.md` (Functional and Non-Functional Requirements)

Structure: purpose and scope, stakeholders and personas, glossary link, assumptions, constraints, out-of-scope, then:

**Functional requirements (FR)**
- Each requirement has a unique ID (`FR-<AREA>-<NNN>`), a clear statement ("The system shall..."), MoSCoW priority, and **testable acceptance criteria** (Given/When/Then).
- Cover at least these areas, expanding the seed list below: ingestion (`FR-ING`), query and answer generation (`FR-QRY`), citations and grounding (`FR-CIT`), conversations (`FR-CNV`), tenancy, auth and roles (`FR-AUTH`), admin and quarantine review (`FR-ADM`), feedback (`FR-FBK`), knowledge-base management (`FR-KB`), evaluation (`FR-EVL`), usage/quotas/cost (`FR-USG`), web UI (`FR-UI`), notifications/status (`FR-STA`).
- Seed examples to refine (not exhaustive): upload PDF/DOCX/TXT/MD/HTML up to a configured size; track ingestion status and errors per document; delete a document and all derived data; answer only from permitted collections with verifiable citations; refuse when evidence is insufficient; stream answers; support follow-up questions in a conversation; users only see their tenant's data; admins can review quarantined content; users can rate answers; admins can view usage and cost per tenant; the UI supports English and Swahili.

**Non-functional requirements (NFR)**
- Each NFR has an ID (`NFR-<CATEGORY>-<NNN>`), a **measurable target**, how it will be measured, and how it will be verified (test, load test, monitoring, review). No vague wording such as "fast" or "secure".
- Cover at least: performance, scalability and capacity, availability and reliability, durability and disaster recovery (RPO/RTO), security, privacy and compliance, AI safety, RAG quality, accessibility, usability, maintainability, testability, observability, portability, compatibility (browsers/devices), cost, and operability.
- Propose sensible defaults for the v1 targets below, clearly marked **"proposed, confirm with owner"**, and list the open questions for the owner:
  - Availability: 99.5% monthly for the API (staging excluded). RPO <= 24h, RTO <= 4h.
  - Latency: p95 time-to-first-token <= 3s and p95 full answer <= 10s for a typical query (excluding provider outages); p95 non-LLM API endpoints <= 300ms.
  - Capacity assumptions: e.g. 100 concurrent chat users, 10 tenants, up to 1M chunks total, ingestion of a 100-page PDF within 2 minutes (state assumptions explicitly and how the design scales beyond them).
  - RAG quality: targets for recall@k, groundedness/faithfulness, citation accuracy and refusal accuracy on the golden dataset (set initial thresholds after a baseline run).
  - Security/AI safety: red-team Attack Success Rate thresholds, zero cross-tenant leakage in tests.
  - Accessibility: WCAG 2.2 AA. Browser support matrix.
  - Cost: maximum average LLM+embedding cost per query and per tenant per month (to be set by the owner); infrastructure budget per environment.
  - Maintainability: coverage >= 80%, no layering violations, complexity limits.

**Traceability**
- A requirements traceability matrix (`docs/TRACEABILITY.md`, can be generated): requirement ID -> component(s) -> API endpoint(s) -> test(s) -> monitoring/SLO. Tests reference requirement IDs (e.g. a `req` marker or naming convention) and a CI check fails on requirements with no test or tests referencing unknown IDs.

### Deliverable 2: `docs/API_DESIGN.md` plus `api/openapi.yaml` (API Architecture Design, design-first)

The API contract is designed and reviewed **before** implementation. `api/openapi.yaml` (OpenAPI 3.1) is the source of truth; server code, tests and the UI client types are generated from or validated against it.

`docs/API_DESIGN.md` must include:
1. **Architectural style and rationale**: REST over HTTPS + SSE for streaming, async job pattern for ingestion; why not GraphQL/gRPC (ADR).
2. **Resource model** with a diagram: tenants, collections, documents, jobs, conversations, messages, queries, feedback, api-keys, admin resources.
3. **Endpoint catalog** (table): method, path, purpose, required scope/role, idempotency, request schema, response schema, error codes, rate-limit class, related FR IDs. Include the full set needed by the UI (Section 10A) and the health/metrics endpoints.
4. **Schemas and examples** for every request/response, with realistic examples, and the **SSE event contract** for streaming (event names, payloads, ordering, error and termination semantics, reconnection behavior).
5. **Authentication and authorization**: API keys for machine clients, BFF session for the UI, scopes/roles matrix per endpoint, tenant resolution, and how RLS (Section 5A) is bound to the request context.
6. **Conventions**: URL naming, versioning (`/v1`) and deprecation/sunset policy, cursor pagination, filtering and sorting, idempotency keys (for uploads and other unsafe operations), conditional requests/ETags where useful, request/response size limits and timeouts, correlation headers (`X-Request-ID`, trace context), rate-limit and quota headers.
7. **Error model**: RFC 9457 problem-details with a catalog of stable, machine-readable error codes, each mapped to HTTP status, meaning, and client guidance.
8. **Async and long-running operations**: 202 + job resource + polling (optional webhooks later), status state machine diagram, retry and cancellation semantics.
9. **File upload design**: multipart limits, allowed types, content sniffing, virus-scan hook, storage flow, resumability decision (ADR).
10. **Sequence diagrams (Mermaid)** for key flows: upload and ingest, query with streaming and citations, delete cascade, quarantine review, feedback, auth/session.
11. **Security considerations per endpoint** (abuse cases, input limits, tenant isolation checks) and links to Section 5/5A controls.
12. **Compatibility and governance**: breaking-change policy, API review checklist, and CI tooling: OpenAPI lint (e.g. Spectral), **breaking-change detection** against the previous contract (e.g. oasdiff), and **contract/property testing of the running API against the spec** (e.g. Schemathesis). A mock server from the spec (e.g. Prism) lets the UI be developed in parallel.

### Deliverable 3: Architecture and decisions
- `docs/ARCHITECTURE.md` and the initial ADRs (Section 0 rule 1), consistent with the requirements and API design, including a mapping from NFRs to architectural decisions (e.g. which design choice satisfies which NFR and its trade-offs).
- `docs/UX.md` outline (personas, key flows) to be completed in Milestone 8, with the personas and flows already aligned to the FRs.

### Phase 0 exit criteria
- [ ] `docs/REQUIREMENTS.md` complete: all FRs have acceptance criteria; all NFRs have measurable targets and verification methods; open questions listed.
- [ ] `docs/API_DESIGN.md` and a lint-clean `api/openapi.yaml` complete and consistent with the FRs; every FR maps to endpoints or components in the traceability matrix.
- [ ] `docs/ARCHITECTURE.md` and initial ADRs written and consistent with the NFRs.
- [ ] A short Phase 0 summary posted for the owner, listing assumptions, open questions and risks. **Then stop and wait for explicit approval.**

## 1. Goals and non-goals

**Goals**
- Ingest documents (PDF, DOCX, TXT, MD, HTML), chunk, embed, and index them.
- Answer questions grounded in the documents with **citations** (document, page/section, chunk id).
- Say "I don't know" when retrieved context is insufficient (no hallucinated answers).
- Multi-tenant ready (tenant/collection isolation), authenticated API.
- Reproducible infra with Terraform; one-command deploy to Render.

**Non-goals (v1)**: fine-tuning models, multi-region. (The web UI is IN scope: see Section 10A.)

## 2. Tech stack (defaults; justify any change in an ADR)

- **Language**: Python 3.12, managed with `uv`.
- **API**: FastAPI + Pydantic v2, async, served by Uvicorn/Gunicorn.
- **Vector store**: PostgreSQL with `pgvector` (HNSW index) on Render Postgres. Also use Postgres full-text search (`tsvector`) for keyword search.
- **Retrieval**: hybrid search (dense + BM25/FTS) merged with Reciprocal Rank Fusion, then an optional reranker (pluggable, behind an interface).
- **Embeddings & LLM**: provider-agnostic interfaces (`EmbeddingProvider`, `LLMProvider`) with at least one concrete implementation selected by env var (e.g. OpenAI or Anthropic for generation; OpenAI or a hosted embedding model for embeddings). Include timeouts, retries with exponential backoff + jitter, and a circuit breaker.
- **Async ingestion**: background worker with a job queue. Use Redis (Render Key Value) + a queue library (e.g. ARQ or RQ); see Section 6B for the Redis architecture. Ingestion must never block the API.
- **ORM/migrations**: SQLAlchemy 2.0 (async) + Alembic.
- **Object storage for raw files**: S3-compatible interface (`BlobStore`) with an implementation for S3/R2 and a local-disk implementation for dev. (Render disks are not shared across services, so do not rely on them for uploads.)
- **Redis**: Render Key Value, two instances (`rag-state` with `noeviction` for queue/locks/quotas/flags, `rag-cache` with `allkeys-lru` for caches); see Section 6B.
- **Observability**: structured JSON logs (structlog), OpenTelemetry traces, Prometheus-style metrics endpoint, request IDs; **LangSmith Cloud** for LLM-specific tracing, cost, evals and feedback (Section 6A); **Grafana** (Cloud + Alloy) for metrics, logs, traces, dashboards and alerting (Section 6C).
- **Quality tooling**: ruff, mypy (strict), pytest, pytest-asyncio, coverage >= 80%, pre-commit.

## 2A. AI System Design Principles (must be visibly implemented)

These principles drive every design decision. For each one, the code, tests and docs must show WHERE and HOW it is implemented, and the README must contain a table mapping principle -> implementation -> file/module.

1. **Grounding over fluency**: answers must be supported by retrieved evidence with verifiable citations; refuse when evidence is insufficient. Explicit uncertainty is a feature.
2. **Deterministic scaffolding around non-deterministic components**: wrap the LLM with validation, schemas, retries, thresholds and fallbacks. Business rules never live inside prompts alone.
3. **Evaluation-driven development**: write/extend evals before changing retrieval, prompts or models. Regressions block merges.
4. **Observability by default**: every request produces a full trace (retrieval candidates, scores, prompt version, model, tokens, cost, latency, verdicts). If you cannot see it, you cannot fix it.
5. **Model and provider agnosticism**: LLM, embeddings, reranker, vector store and blob store sit behind ports (interfaces). Swapping a provider must be a config change plus one adapter.
6. **Version everything**: prompts, models, embedding model + dimension, chunking config, index version, eval datasets, configs. Every answer log records the versions used so results are reproducible.
7. **Safe re-indexing**: changing the embedding model or chunking strategy must support a blue/green index (build new index alongside, evaluate, switch, rollback). Document the procedure.
8. **Graceful degradation**: define fallback modes (cached answer, retrieval-only with snippets, smaller/cheaper model, secondary provider) triggered by circuit breakers or a kill switch. The system must degrade, not crash.
9. **Cost and latency as design constraints**: token budgets, context packing, caching, batching, model routing (cheap model for rewriting/classification, stronger model for final answer). Track cost per request, per tenant.
10. **Separation of retrieval and generation**: they are independently testable, measurable and replaceable. Retrieval quality is measured without calling the generator.
11. **Defense in depth and least privilege**: see Section 5 and 5A. Assume components fail or get manipulated.
12. **Data quality is a first-class concern**: parsing quality, chunk boundaries, metadata, deduplication and freshness are tested and measured, not assumed.
13. **Human-in-the-loop and feedback loops**: user feedback, admin review of quarantined content, and failed/low-confidence queries feed back into the eval dataset.
14. **Idempotency, async and backpressure**: ingestion is asynchronous, idempotent and resumable; queues have limits and dead-letter handling.
15. **Privacy by design**: data minimization, tenant isolation, retention and deletion are built in from the start.
16. **Progressive complexity**: start with the simplest pipeline that works, measure, and add components (hybrid search, reranking, query rewriting, caching) only when evals show a gain. Record the measured gain in an ADR.
17. **Config-driven experimentation**: retrieval/prompt/model variants selectable by config, supporting A/B and shadow evaluation without code changes.

## 2B. Software Engineering Principles (mandatory, enforced automatically)

Code quality is a requirement, not a preference. Apply these principles throughout backend, infrastructure and UI code. Where a principle is only a guideline, add an automated check or a review-checklist item so it is actually enforced. The README must contain a table: principle -> how it is applied -> where to see it.

**Design principles**
1. **SOLID**: single responsibility per module/class; open for extension via ports and adapters (new provider = new adapter, no edits to services); Liskov-safe interface implementations (fakes and real adapters pass the same contract tests); small, focused interfaces; depend on abstractions (dependency inversion via DI).
2. **Separation of concerns and high cohesion / low coupling**: API layer, use-cases, domain and adapters never leak into each other (rules in Section 3).
3. **KISS, YAGNI, DRY (applied with judgment)**: simplest design that meets the requirement; no speculative abstractions; remove real duplication but do not create premature abstractions. Every design pattern used (Repository, Strategy, Factory, Adapter, Circuit Breaker, Decorator for caching/tracing, etc.) must solve a concrete problem and be named in docs.
4. **Domain-driven design (lite)**: a ubiquitous language (glossary in `docs/GLOSSARY.md`), clear bounded contexts (ingestion, retrieval, generation, evaluation, tenancy/auth), entities and value objects in the domain layer, invariants enforced in the domain, not in routers.
5. **Make illegal states unrepresentable**: use strict types, enums, Pydantic/Zod models and value objects; parse and validate at the boundaries, trust typed data inside.
6. **Fail fast, explicit error handling**: a typed exception hierarchy mapped to **RFC 9457 problem-details** HTTP errors; no bare `except`, no swallowed errors; never use exceptions for normal control flow.
7. **Immutability and pure functions** where practical (chunking, ranking, prompt assembly are pure and easy to test); isolate side effects at the edges.
8. **Principle of least astonishment** and consistent naming conventions (documented), small functions, meaningful names, no magic numbers (named constants/config).

**Service and API engineering**
9. **Twelve-Factor App**: config in environment (validated at startup by pydantic-settings, fail fast on missing/invalid config), stateless processes, backing services as attachable resources, logs to stdout, dev/prod parity, disposable processes with graceful shutdown, admin tasks (migrations) as one-off commands.
10. **API design**: resource-oriented REST under `/v1`, consistent naming, cursor pagination, filtering, idempotency keys for unsafe operations (uploads), correct status codes, rate-limit headers, backward-compatible evolution with a deprecation policy, and OpenAPI as the contract. Add **contract tests** so the UI/API cannot drift.
11. **Backward-compatible database migrations** (expand -> migrate -> contract), reversible where possible, tested on a copy of realistic data, safe for zero-downtime deploys; no destructive change in the same release as the code that stops using it.
12. **Resilience patterns**: timeouts everywhere, retries only for idempotent calls with backoff and jitter, circuit breakers, bulkheads/concurrency limits, graceful degradation (Section 2A #8).
13. **Concurrency correctness**: async code never blocks the event loop (offload CPU-bound parsing/embedding work), no shared mutable global state, explicit transaction boundaries, optimistic concurrency where needed.

**Process and quality**
14. **Testing pyramid and TDD where it pays**: many fast unit tests, fewer integration tests (real Postgres/Redis in containers), few e2e tests. Test behavior, not implementation. Contract tests for every port (real adapter and fake pass the same suite). Property-based tests (Hypothesis) for chunking, RRF and token budgeting. Deterministic tests: no real network or LLM calls in unit tests (use recorded/fake providers). Coverage >= 80% with meaningful assertions; consider mutation testing (e.g. mutmut) on core logic.
15. **Static analysis and automatic enforcement (CI-blocking)**:
    - ruff (lint + format), mypy `--strict`, complexity limits (cyclomatic complexity cap via ruff `C901`), maximum function/file size guidance.
    - **`import-linter` contracts that enforce the layering** (domain imports nothing from adapters/api; services do not import api; etc.). A violation fails CI.
    - Frontend: ESLint, Prettier, TypeScript strict, no `any` without justification.
    - Secret scanning (gitleaks), dependency and license checks, dead-code detection (vulture or similar).
16. **Version control discipline**: trunk-based development with short-lived branches, small PRs, Conventional Commits, Semantic Versioning, automated `CHANGELOG`, protected `main` (required checks, review), `CODEOWNERS`, PR template with a checklist (tests, docs, security, migrations, observability, rollback).
17. **Documentation as part of the code**: docstrings for public APIs and non-obvious decisions (explain *why*, not *what*), ADRs for significant decisions, runbooks, and docs-as-code checks in CI.
18. **Safe delivery**: feature flags for risky changes, progressive rollout (staging -> production), health-gated deploys, documented rollback, and a post-deploy smoke test.
19. **Measure before optimizing**: no performance work without a benchmark or profile; record baselines and regressions (load tests, query plans with `EXPLAIN ANALYZE` for pgvector/FTS queries).
20. **Technical debt management**: track known shortcuts in `docs/TECH_DEBT.md` with context and a trigger for repayment; no unexplained `TODO`s (each links to an issue or ADR); refactor continuously under test coverage.
21. **Supportability**: every error is actionable (clear message, correlation ID), every alert has a runbook, every component has a health check, and the system is operable by someone who did not write it.

**Anti-over-engineering guard:** YAGNI wins when in doubt. If a principle seems to demand more complexity than the current requirement justifies, choose the simpler option and record the reasoning in an ADR.

## 3. Architecture requirements

Use clean/hexagonal architecture:

```
src/rag/
  api/            # FastAPI routers, schemas, dependencies, middleware
  core/           # config (pydantic-settings), logging, security, errors
  domain/         # entities, value objects, interfaces (ports)
  services/       # ingestion, retrieval, generation, evaluation (use-cases)
  adapters/       # pgvector repo, blob store, embedding/LLM providers, queue
  workers/        # background job handlers
  db/             # models, migrations
tests/
  unit/ integration/ e2e/ eval/
infra/
  terraform/      # see section 8
docs/
```

Rules: domain has no framework imports; adapters implement ports; dependency injection via FastAPI dependencies; no business logic in routers.

### Ingestion pipeline
1. `POST /v1/documents` (multipart or URL) -> store raw file in `BlobStore`, create `documents` row with status `queued`, enqueue job, return `202` with job id.
2. Worker: parse -> clean -> chunk (recursive/semantic-aware, configurable size/overlap, preserve headings/page metadata) -> embed in batches -> upsert chunks. Idempotent (content hash dedup), resumable, with status transitions `queued -> processing -> ready | failed` and error details.
3. `GET /v1/jobs/{id}`, `GET /v1/documents`, `DELETE /v1/documents/{id}` (cascade chunks).

### Query pipeline
1. `POST /v1/query` with `{question, collection_id, top_k, filters, stream}`.
2. Query rewriting (optional, configurable) -> hybrid retrieve -> RRF -> rerank -> context assembly under a token budget -> grounded prompt -> LLM -> answer with citations.
3. Support **streaming** (SSE). Return `answer`, `citations[]`, `retrieval_debug` (only when a debug flag + admin scope), latency and token usage.
4. Guardrails: prompt-injection-resistant prompt structure (retrieved text is untrusted data, clearly delimited), max input size, output citation validation, refusal when no relevant context (similarity/rerank score threshold).
5. Cache: semantic/exact cache for repeated queries (Key Value store) with TTL and tenant-scoped keys.

## 4. Data model (minimum)

`tenants`, `api_keys` (hashed), `collections`, `documents` (hash, status, metadata, source), `chunks` (text, embedding `vector(N)`, tsvector, page, section, metadata JSONB, document_id, collection_id), `jobs`, `conversations`, `messages`, `query_logs` (question, retrieved ids, latency, tokens, feedback). Index: HNSW on embedding, GIN on tsvector and metadata. All queries scoped by tenant/collection. Include Alembic migrations and a migration that runs `CREATE EXTENSION IF NOT EXISTS vector`.

## 5. Security

- API key auth (hashed in DB, scoped: `read`, `write`, `admin`) and rate limiting per key.
- Strict input validation, file type/size limits, virus-scan hook (interface), safe file parsing.
- CORS allow-list, security headers, no stack traces to clients, PII-safe logging (redact).
- Secrets only via environment (Render env groups), never in code or Terraform state in plaintext where avoidable (mark variables `sensitive`).
- Dependency scanning (pip-audit) and a basic threat model in `docs/SECURITY.md`.
- **Public repository safety** (the GitHub repository may be PUBLIC; assume everything committed is world-readable forever and scraped by bots within minutes):
  - Never commit secrets, real customer documents, real user data, production IDs/tokens, `.env`, `*.tfvars` with values, Terraform state, or logs. Test fixtures and the golden dataset must be **synthetic or properly licensed** content only.
  - Enable GitHub secret scanning and **push protection**, Dependabot alerts/updates, and code scanning (CodeQL) on the repository; run gitleaks in CI and as a pre-commit hook. If a secret is ever committed, treat it as compromised: **rotate it immediately** (deleting it from history is not enough).
  - CI on a public repo: no secrets are available to workflows triggered by forks; never use `pull_request_target` with checkout of untrusted PR code; pin third-party actions to commit SHAs; set minimal `permissions:` per workflow and job; require approval to run workflows from outside contributors; keep secrets only in GitHub **Environments** (staging, production) with required reviewers for production; do not post `terraform plan` output to PR comments (it can reveal infrastructure details), upload it as a protected artifact or summarize without sensitive values.
  - Keep infrastructure identifiers and sensitive operational detail (account IDs, internal hostnames, real tenant names) out of docs, ADRs, screenshots and READMEs. The security design may be public, secrets and live details may not.
  - Choose and add a `LICENSE` deliberately (a public repo without a license is "all rights reserved"; use e.g. Apache-2.0 or MIT if open source is intended, or state the proprietary terms).

## 5A. LLM and AI Security (mandatory, defense in depth)

Treat this as a first-class subsystem, not an afterthought. Map every control to the **OWASP Top 10 for LLM Applications (2025)**, **MITRE ATLAS** and the **NIST AI RMF**, and document the mapping as a table in `docs/AI_SECURITY.md`.

**Core principle:** no single control fully prevents prompt injection. Assume the model WILL be manipulated at some point. Design so that a manipulated model has a tiny blast radius: no tools, no secrets, strict tenant isolation, validated outputs.

### Threats to model explicitly
- Direct prompt injection and jailbreaks via user query.
- **Indirect prompt injection**: malicious instructions hidden inside ingested documents, web pages, or metadata (including hidden text, HTML comments, zero-width/Unicode tricks, white-on-white text, PDF annotations).
- RAG/knowledge-base poisoning and embedding-space attacks.
- Data exfiltration through model output (markdown images, links, URLs with encoded data, tool calls).
- Cross-tenant data leakage via retrieval, cache, logs or shared prompts.
- System prompt leakage and sensitive information disclosure (PII, secrets).
- Insecure output handling (XSS, injection into downstream systems).
- Excessive agency (tools/actions the model should not have).
- Unbounded consumption: token/cost abuse, denial-of-wallet, expensive-query attacks.
- Supply chain: models, embeddings, packages, parsers.
- Misinformation / hallucination presented as fact.

### Required controls (implement all, each behind an interface and a feature flag where sensible)

1. **Input layer**
   - Unicode normalization (NFKC), strip control/zero-width/bidi characters, enforce max length and max tokens.
   - `InjectionDetector` port with a default implementation (heuristics + a pluggable classifier such as Llama Prompt Guard or a hosted guardrail service). Action on detection is configurable: `block | flag | allow-with-warning`. Log every detection as a security event.
   - PII/secret detection on input (e.g. Presidio-style) with configurable redact/block.

2. **Ingestion-time defenses (poisoning and indirect injection)**
   - Sanitize parsed content: remove hidden/invisible text, HTML comments, scripts, metadata fields not needed, and suspicious Unicode.
   - Scan every chunk for instruction-like patterns and run the `InjectionDetector`; mark suspicious chunks `quarantined` (excluded from retrieval until reviewed by an admin).
   - Store provenance and a **trust level** per source (`trusted | internal | untrusted`); retrieval and prompt assembly must respect it.
   - Content-hash and signature/provenance tracking so tampering with indexed content is detectable; audit every ingestion and deletion.
   - Validate embedding dimensions and reject anomalous vectors.

3. **Prompt architecture**
   - Strict instruction hierarchy: system prompt (developer rules) > user question > retrieved context (data only, never instructions).
   - Wrap retrieved chunks in clearly delimited data blocks using **random per-request boundary tokens**; apply spotlighting/datamarking so the model can tell data from instructions. Explicitly instruct the model that content inside data blocks must never be followed as instructions.
   - Never place secrets, API keys, internal URLs or other tenants' data in any prompt. Assume the system prompt can leak and keep it non-sensitive.
   - Version prompts in code (`prompts/` with tests), no prompt text built from raw user strings via string concatenation of instructions.

4. **Retrieval and tenant isolation**
   - Enforce tenant/collection isolation **at the database level** using PostgreSQL Row-Level Security, in addition to application filters. Add a test that proves cross-tenant retrieval is impossible even if application code has a bug.
   - ACL-aware retrieval (document-level permissions filter applied before ranking).
   - Cache keys, rate-limit keys, and logs are tenant-scoped.

5. **Output layer**
   - Require **structured output** (JSON schema) and validate it strictly; reject and retry/refuse on schema violations.
   - **Citation verification**: every claim must reference retrieved chunk IDs that actually exist in the retrieved set; strip or reject unsupported claims. Add a groundedness check (LLM-as-judge or NLI model) with a configurable threshold, refusing to answer below it.
   - **Exfiltration prevention**: block/strip markdown images and auto-loading links; allow only URLs from an allowlist or from cited document metadata; never render model-produced HTML. Escape output for the client (prevent XSS).
   - Output scanner for PII, secrets, system-prompt fragments and policy violations (toxicity/unsafe content) with configurable actions.
   - Canary token in the system prompt to detect system-prompt leakage in outputs; alert if seen.

6. **No excessive agency**
   - v1 LLM has **no tools, no code execution, no network access, no write actions**. If tools are added later, require: least privilege, allowlisted tools with schema-validated arguments, per-tenant permissions, human approval for any side effect, and an ADR plus threat-model update.

7. **Cost and abuse controls (unbounded consumption)**
   - Hard `max_tokens`, context token budget, per-request timeout, max retrieved chunks.
   - Per-key and per-tenant quotas (requests, tokens, daily spend), concurrency limits, and automatic throttling.
   - Spend caps configured at the LLM provider, budget alerts, and a kill switch (feature flag) to disable generation or switch to retrieval-only mode.

8. **Model and provider security**
   - Pin model versions explicitly; test before upgrading (eval + red-team suite must pass).
   - Separate provider API keys per environment with least privilege, rotation procedure documented, never logged.
   - Prefer providers/settings with zero data retention and no training on customer data; document DPA/compliance status.
   - Supply chain: hash-pinned dependencies (`uv` lockfile), SBOM generation (CycloneDX), `pip-audit`, never use `pickle` or `trust_remote_code`, only load models from verified sources, scan Docker images (Trivy/Grype).

9. **Monitoring, detection and response**
   - Emit structured **security events** (injection detected, output blocked, quarantined chunk, quota exceeded, canary leaked, cross-tenant attempt) with tenant, key, request ID. Never log raw sensitive content; redact first.
   - Metrics and alerts: injection-detection rate, block rate, groundedness refusals, anomalous token usage, spikes per key.
   - Incident response runbook in `docs/RUNBOOK_AI_INCIDENTS.md` (key revocation, quarantine a document, disable generation, purge cache, notify).

10. **Privacy and data lifecycle**
    - Configurable retention for queries, logs and raw files. Deletion requests must cascade to: raw blob, chunks, embeddings, caches, query logs, and derived artifacts. Add a test.
    - Encryption in transit (TLS) and at rest for DB, blob storage and backups.

11. **Continuous AI red teaming (in CI)**
    - `tests/security/` containing an adversarial suite: direct injections, jailbreaks, indirect-injection fixtures (poisoned PDFs/HTML/DOCX with hidden text), exfiltration attempts (markdown image/link payloads), system-prompt extraction attempts, cross-tenant probes, cost-abuse prompts, multilingual and encoded attacks (base64, leetspeak, Swahili and other languages).
    - Use tools such as **garak**, **promptfoo** or **PyRIT** where practical, plus custom tests. Report **Attack Success Rate** per category; CI fails if it exceeds configured thresholds. Run on every PR (smoke) and nightly (full).

12. **Governance and documentation**
    - `docs/AI_SECURITY.md`: threat model, OWASP LLM Top 10 mapping table, control inventory, residual risks, and an honest statement of limitations.
    - `docs/MODEL_CARD.md`: models used, versions, intended use, known limitations.
    - Security review checklist in the PR template for any prompt, retrieval or model change.

## 6. Reliability and performance

- Health endpoints: `/healthz` (liveness), `/readyz` (checks DB, queue, blob store).
- Graceful shutdown, DB connection pooling, per-request timeouts, backpressure on ingestion, dead-letter handling for failed jobs.
- Document SLOs (e.g. p95 query latency, availability) and how metrics map to them in `docs/SLO.md`.
- Include a load-test script (k6 or locust) and record baseline results.

## 6A. LLM Observability with LangSmith (Cloud)

Use **LangSmith Cloud** (the managed service from LangChain) as the LLM-specific observability, evaluation and feedback layer. LangChain and LangGraph are NOT required: use the standalone `langsmith` Python SDK (`@traceable`, provider wrappers such as `wrap_openai` / `wrap_anthropic`, the `Client` for feedback and datasets), and optionally its OpenTelemetry ingestion. Check the current official LangSmith docs before coding, because SDK APIs and environment variable names change.

**Division of responsibility (important):**
- **LangSmith** answers: *what did the model do and why?* (LLM traces, prompts, token/cost per call, eval experiments, feedback, human review).
- **Grafana** (Section 6C) answers: *how is the system performing?* (metrics, logs, infrastructure, SLOs, alerts).
Do not duplicate data between them. Link them via shared IDs.

Requirements:
- Behind an `LLMTracer` port with a LangSmith adapter and a no-op adapter, switchable by env var. **A LangSmith outage must never break or slow a user request**: use background/batched export, short timeouts, swallow-and-log errors, and expose a metric `rag_tracing_export_failures_total`.
- Configuration via environment variables (names per current docs, e.g. `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`). Use **one LangSmith project per environment** (e.g. `rag-staging`, `rag-production`). Choose the US or EU endpoint according to data residency needs and record it in an ADR.
- One trace per API request with nested runs: query rewrite, embedding call, vector search, keyword search, RRF, rerank, context assembly, LLM generation, guardrail checks, citation verification, groundedness check.
- Per LLM run record: model name and version, prompt version, masked input/output, token usage, latency, cost, finish reason. Retrieval runs record chunk IDs and scores, not raw sensitive text. Tag runs with tenant (hashed if required), environment, release version, collection, and index/embedding version.
- Attach **feedback/scores** to runs using the LangSmith feedback API: groundedness, citation accuracy, user feedback (from `POST /v1/feedback`), guardrail verdicts, and eval results.
- **Correlation**: `request_id`, OpenTelemetry `trace_id` and the LangSmith run ID must all appear in structured logs, so any answer can be followed from a Grafana alert to the exact LLM trace.
- **Privacy**: apply the PII/secret `mask` function (Section 5A) through the SDK's input/output hiding hooks (e.g. `hide_inputs` / `hide_outputs` or equivalent) so unmasked content never leaves your infrastructure. Hash user identifiers, support per-tenant opt-out and a sampling rate, configure retention in LangSmith, and document how trace data is deleted when a deletion request cascades (Section 5A). Document exactly what data is sent to LangSmith and confirm DPA/compliance status.
- **Datasets and experiments**: the evaluation harness (Section 7) uses LangSmith datasets and `evaluate()` experiments so runs are comparable across prompt, model and retrieval versions. CI reads experiment results and fails on regressions.
- **Prompts**: the repo remains the source of truth for prompts (versioned, tested). Optionally sync to the LangSmith prompt hub; pin versions per release and never fetch "latest" at runtime in production.
- **Human review loop**: use LangSmith annotation queues for low-groundedness, refused, or negative-feedback traces; reviewed items are promoted into the golden dataset (principle 13).
- **Hosting decision (ADR required)**: LangSmith Cloud is the chosen option. Document vendor lock-in mitigation (the `LLMTracer` port and OpenTelemetry keep the app portable) and the alternative of a self-hosted tracer.
- Terraform passes `LANGSMITH_API_KEY` and related settings as `sensitive` environment variables. Never log them.

## 6B. Redis (Render Key Value) Architecture

Redis is a core component, not an optional extra. Define it explicitly and test it.

**Use two separate Render Key Value instances**, because queue/control data and cache data need different eviction policies:

1. `rag-state` (maxmemory policy **`noeviction`**; enable persistence where the plan supports it): job queue (ARQ or RQ), retry schedules, dead-letter queue, ingestion idempotency/dedup keys, distributed locks, rate-limit counters, tenant quotas and spend counters, circuit-breaker state, kill-switch and feature flags. These must never be silently evicted.
2. `rag-cache` (maxmemory policy **`allkeys-lru`**): exact query cache, semantic query cache, retrieval-result cache, embedding cache (key = hash of text + embedding model version, with TTL). Cache loss must only cost latency, never correctness.

Rules:
- Access only through ports with Redis adapters and in-memory fakes for tests: `QueueBackend`, `CacheStore`, `RateLimiter`, `QuotaStore`, `FeatureFlags`, `LockManager`.
- Key naming: `rag:{env}:{tenant_id}:{domain}:{key}`. **Every cache key has a TTL.** Cache keys include versions (embedding model, prompt version, index version, collection id) so a version change invalidates entries automatically. No unbounded key growth.
- **Security and privacy**: keys are tenant-scoped; never serve a cached answer across tenants or across different ACL scopes; invalidate cache entries when a document is updated, quarantined or deleted (track entries per document/collection with tag sets or a per-collection version counter); deletion cascade (Section 5A) must purge Redis too; keep TTLs short for answers that may contain PII.
- **Connectivity**: use the Render private network internal URL, TLS (`rediss://`) where supported, authentication, and a locked-down IP allowlist (no public access). Use `redis-py` asyncio with a shared connection pool, timeouts, retries with backoff, and periodic health checks. Redis URLs are secrets.
- **Defined failure modes** (document and test with fault-injection tests):
  - cache unavailable -> bypass the cache (fail open), log and count it;
  - rate limiter/quota store unavailable -> configurable; default to a conservative in-process limiter for expensive endpoints;
  - queue unavailable -> `POST /v1/documents` returns `503` with `Retry-After`, readiness (`/readyz`) reports not ready;
  - feature flags unavailable -> use last-known values, falling back to safe defaults.
- **Semantic cache**: store the query embedding, answer, citations and versions; use a conservative similarity threshold; re-verify that cited chunks still exist and are not quarantined before serving; allow disabling per tenant; track hit ratio and the quality impact in evals.
- **Observability** (see 6C): memory used, evictions (alert on any evictions in `rag-state`), hit ratio, ops/sec, connected clients, latency, queue depth, oldest job age, DLQ size.
- `docker-compose.yml` runs two Redis containers (or two configurations) to mirror production semantics.
- Document sizing and a memory estimate (especially for the embedding cache) in the README operations section.

## 6C. Monitoring and Observability with Grafana

Build full monitoring with the Grafana stack: **Grafana Cloud** (recommended for v1; check current free-tier limits) providing Prometheus-compatible metrics, Loki for logs, Tempo for traces, and Grafana Alerting. A self-hosted Grafana on Render is an alternative (more operations: persistent disk, backups, upgrades); record the decision in an ADR.

### Architecture
- The API and worker expose Prometheus-format `/metrics` on an internal or authenticated path (never publicly exposed) and export OpenTelemetry traces and logs. Instrument FastAPI, SQLAlchemy/asyncpg, Redis and the HTTP client with OpenTelemetry.
- Deploy **Grafana Alloy** as a Render private service (managed by Terraform) to scrape the API, worker, Redis exporter and Postgres exporter, receive OTLP, and forward everything to Grafana Cloud. Check whether Render Log Streams and Metrics Streams can send data directly (or into Alloy) and use them where they exist, to reduce moving parts. Verify current capabilities in the Render and Grafana docs rather than assuming.
- **Monitoring as code**: provision Grafana folders, dashboards (JSON in `infra/grafana/dashboards/`), alert rules, contact points and notification policies with the Grafana Terraform provider (`grafana/grafana`). Dashboards and alerts are reviewed in PRs. CI validates dashboard JSON and runs a lint.
- **Local development**: a `docker compose --profile observability` setup (for example Prometheus, Loki, Tempo and Grafana, or the all-in-one `grafana/otel-lgtm` image) with the same dashboards provisioned, so dashboards are developed and tested locally.

### Metrics to instrument (prefix `rag_`, histograms for latency)
- **API (RED)**: request rate, error rate by status class, latency histogram per route.
- **Pipeline steps**: latency histograms for rewrite, embed, vector search, keyword search, rerank, generation (time to first token and total), guardrails.
- **LLM and cost**: input/output tokens, estimated cost, provider errors, retries, circuit-breaker state, fallback-mode activations.
- **RAG quality signals**: empty-retrieval rate, refusal ("I don't know") rate, groundedness score distribution, citation validation failures, feedback ratio, cache hit ratio (exact and semantic).
- **Ingestion**: jobs by status, queue depth, oldest job age, processing duration, failure rate, DLQ size, chunks per document.
- **Redis**: memory, evictions, hit ratio, clients, latency (Section 6B).
- **Postgres**: connections vs limit, query latency including pgvector search, slow queries, disk, replication/backup status where available.
- **Security events** (Section 5A): injection detections, blocked outputs, quarantined chunks, quota exceeded, cross-tenant attempts, **canary leaks**.
- **Tracing health**: LangSmith export failures, OpenTelemetry export failures.
- **Label cardinality rules**: bounded labels only (route, status class, step, provider, model, environment, tenant only if the tenant count is bounded). Never label by user ID, query text, request ID or document ID. Document this in the README.

### Dashboards (as code)
1. **Service overview** (RED, saturation, deploy annotations).
2. **RAG pipeline** (per-step latency, retrieval quality signals, refusal and groundedness trends).
3. **LLM and cost** (tokens, cost per tenant/day, provider errors, fallbacks).
4. **Ingestion** (queue depth, job age, failures, DLQ).
5. **Redis** and 6. **Postgres/pgvector**.
7. **Security** (AI security events, auth failures, rate limiting).
8. **SLO** dashboard (SLIs, error budget, burn rate).
Panels must link out to the relevant LangSmith project and Loki/Tempo views. Enable exemplars so metric spikes link to traces.

### Alerting (symptom-based, with runbook links in every alert)
- Multi-window SLO burn-rate alerts for availability and p95 latency.
- Elevated 5xx rate; provider failure rate; circuit breaker open for too long.
- Queue backlog or oldest-job age above threshold; **any DLQ growth**.
- Redis memory above 80%; **any evictions on `rag-state`**; Redis unreachable.
- Postgres connection saturation, disk usage, slow pgvector queries.
- Cost spike per tenant/day; token usage anomalies.
- Groundedness drop or refusal-rate spike (possible retrieval or index regression).
- Security: spike in injection detections or blocked outputs; **canary leak pages immediately**.
- Tracing export failures; missing metrics (absence alerts for each service).
- Define severities (page vs ticket), contact points (email/Slack/PagerDuty, configurable), and silences/maintenance windows.

### Logs and traces
- JSON logs include `request_id`, `trace_id`, LangSmith run ID, tenant (hashed if needed), route, and version. Use low-cardinality Loki labels (service, environment, level); keep high-cardinality fields as structured metadata or in the log body. Redact PII and secrets before export (Section 5A).
- Enable log-to-trace and trace-to-log links in Grafana.

### Synthetic monitoring
- Uptime checks on `/healthz` and `/readyz`, plus a low-cost synthetic canary query against a dedicated test tenant every few minutes (prefer retrieval-only or a tiny model call to control cost) that alerts on failure or on a sharp quality/latency change.

## 7. Evaluation (RAG quality is a first-class requirement)

- `tests/eval/`: a small golden dataset (questions, expected sources, reference answers) and a script computing retrieval metrics (recall@k, MRR, nDCG) and generation metrics (faithfulness/groundedness, answer relevance, citation accuracy) using an LLM-as-judge behind an interface.
- A CLI `make eval` that outputs a report and fails CI if metrics drop below configured thresholds.
- Log user feedback endpoint (`POST /v1/feedback`) for continuous improvement.

## 8. Infrastructure as code: Terraform on Render

Use the official Render Terraform provider (`render-oss/render`). Layout:

```
infra/terraform/
  versions.tf  providers.tf  variables.tf  outputs.tf
  main.tf                  # or split into modules/
  modules/
    postgres/  keyvalue/  web_service/  worker/  env_group/  alloy/  grafana/
  envs/
    staging.tfvars  production.tfvars   # no secrets inside
  README.md
```

Provision (verify exact resource names in provider docs):
- Render project and environments (staging + production).
- Render Postgres (with pgvector available; document plan size and how to enable the extension via migration).
- Two Render Key Value (Redis-compatible) instances: `rag-state` (`noeviction`) and `rag-cache` (`allkeys-lru`), private network only, per Section 6B.
- Web service for the API (Docker runtime, health check path `/readyz`, autoscaling settings where supported, region variable).
- Background worker for ingestion (same image, different start command).
- Grafana Alloy as a Render private service (collector forwarding metrics, logs and traces to Grafana Cloud), per Section 6C.
- Grafana resources (dashboards, alert rules, contact points, notification policies) via the Grafana Terraform provider (`grafana/grafana`), using JSON from `infra/grafana/`.
- Environment group for shared config; secrets passed as `sensitive` variables (`RENDER_API_KEY`, `RENDER_OWNER_ID`, LLM/embedding keys, S3 credentials, `LANGSMITH_API_KEY`, Grafana Cloud tokens). Redis URLs come from Terraform outputs of the Key Value resources, not from manual copy-paste.
- Web UI service `rag-web` (Next.js BFF, Section 10A) with its own health check and `sensitive` secrets.
- Pre-deploy command to run Alembic migrations.

Requirements:
- Remote Terraform state (document the chosen backend, e.g. S3-compatible/Terraform Cloud) with locking; never commit state.
- `terraform fmt`, `validate`, `tflint` and `tfsec`/`checkov` in CI. `terraform plan` on PRs; `apply` only on merge to main with a manual approval for production.
- Pin provider and Terraform versions.
- Provide a `Dockerfile` (multi-stage, non-root user, small final image, healthcheck) and `.dockerignore`.
- Optionally provide a `render.yaml` Blueprint as a documented alternative, but Terraform is the source of truth.

## 9. CI/CD (GitHub Actions)

- On PR: ruff, mypy, unit + integration tests (use a Postgres+pgvector service container), Docker build, Terraform fmt/validate/plan, pip-audit, eval smoke test.
- On main: build and push image (or let Render build from repo), run `terraform apply` for staging, then promote to production with approval.
- Cache dependencies; keep pipelines fast.

## 10. Developer experience

- `docker-compose.yml` (api, worker, postgres+pgvector, two redis instances mirroring `rag-state` and `rag-cache`, minio) for one-command local run, plus an `observability` profile (Prometheus/Loki/Tempo/Grafana or `grafana/otel-lgtm`) with dashboards provisioned.
- `Makefile` targets: `setup`, `dev`, `test`, `lint`, `typecheck`, `migrate`, `eval`, `load-test`, `tf-plan`, `tf-apply`.
- `.env.example` with every variable documented.
- `README.md` is the **main documentation entry point** and must be polished, well structured and professional (badges, table of contents, consistent headings). It must contain the ENTIRE architecture overview itself, using **Mermaid diagrams** (renderable on GitHub), with deeper dives linked from `docs/`. Required sections, in this order:
  1. Project overview, key features, UI screenshots/GIF (Section 10A), and what problem it solves.
  2. Table of contents, followed by a short requirements summary (key FRs and measurable NFR targets, linking to `docs/REQUIREMENTS.md`) and an API overview linking to `docs/API_DESIGN.md` and the rendered OpenAPI docs.
  3. **Architecture**: system context diagram (C4 level 1), container/component diagram (C4 level 2), ingestion sequence diagram, query sequence diagram (including guardrails, LangSmith tracing, Redis cache and fallbacks), data model ER diagram, Redis usage diagram (which keys live in `rag-state` vs `rag-cache`), monitoring and observability architecture diagram (app -> Alloy -> Grafana Cloud, and app -> LangSmith), deployment diagram (Render services + Terraform + external providers), security architecture and trust boundaries diagram, CI/CD flow diagram.
  4. **AI system design principles** table (Section 2A) and **software engineering principles** table (Section 2B): principle -> how it is implemented/enforced -> module/file/CI-check link.
  5. **AI security** summary and OWASP LLM Top 10 mapping table (link to `docs/AI_SECURITY.md`).
  6. Tech stack table with the reason for each choice, and the ADR index with one-line summaries.
  7. Quickstart (local with docker compose), configuration reference (every env var in a table), and API reference with curl examples (ingest, query, streaming, feedback, errors).
  8. Observability guide: logs, metrics, OpenTelemetry, LangSmith (LLM traces, evals, feedback), Grafana (dashboards, alerts, SLOs), Redis behaviour and failure modes, label-cardinality rules, and how to follow one request end to end from a Grafana alert to the LangSmith trace.
  9. Evaluation guide: how to run evals and red-team suites, metrics definitions, thresholds, latest results.
  10. Deployment guide: Terraform on Render step by step (remote state, variables, plan/apply, staging -> production promotion, rollback), plus cost estimate per environment.
  11. Operations: SLOs, runbooks index, backup/restore, re-indexing (blue/green), scaling notes, disaster recovery.
  12. Project structure tree, testing strategy, contributing, roadmap, known limitations, and license.
  - Keep README and diagrams in sync with the code: add a CI check (e.g. mermaid-cli render and markdown link check) so docs cannot silently rot.
- `CONTRIBUTING.md`, `LICENSE`, `CHANGELOG.md`, PR template.
- API versioned under `/v1` with auto-generated OpenAPI docs.

## 10A. Web UI/UX (mandatory deliverable)

Build a polished, accessible, production-quality web interface for the RAG chatbot. This is a real product surface, not a demo page. Treat design quality, accessibility and security of the UI as seriously as the backend. Before building, load and follow any available frontend-design guidance/skills, and write `docs/UX.md` (user personas, key flows, wireframes or Mermaid flow diagrams, design tokens, and decisions).

### Stack (defaults; justify changes in an ADR)
- **Next.js (App Router) + TypeScript (strict) + Tailwind CSS + shadcn/ui (Radix primitives)**, in a `web/` directory of the monorepo.
- Server state with TanStack Query; streaming via SSE (`fetch` + stream reader); form validation with Zod; Markdown rendering with a **safe** renderer.
- Deployed on Render as its own service (`rag-web`), provisioned by Terraform, with its own Dockerfile or Render native Node runtime.

### Authentication and API access (security-critical)
- **Never ship an API key or secret to the browser.** Use a **backend-for-frontend (BFF)** pattern: the Next.js server holds credentials and proxies calls to the RAG API; the browser only has an HttpOnly, Secure, SameSite session cookie.
- User login via a pluggable auth provider (e.g. OIDC/Auth.js with email or social login); record the choice in an ADR. Map users to tenants and roles (`viewer`, `editor`, `admin`) and enforce them in both the BFF and the backend.
- Same-origin BFF means no permissive CORS. Add CSRF protection for state-changing requests.
- Strict **Content-Security-Policy**, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors`, and other security headers. No inline scripts without nonces.

### Core features
1. **Chat**
   - Streaming answers with token-by-token rendering, a stop/cancel button, retry/regenerate, copy, and edit-and-resend.
   - **Citations are first-class**: inline numbered citations; clicking one opens a side panel showing the source document, page/section, and the cited chunk text with the supporting passage highlighted; link to open the original document.
   - Clear UI states for: loading/retrieving, streaming, **"I don't know / not enough evidence"** (explain why and suggest rephrasing or uploading documents), guardrail refusals, rate limit/quota exceeded, provider fallback mode (e.g. "retrieval-only mode"), network errors, and offline.
   - Thumbs up/down with an optional reason (sent to `POST /v1/feedback`).
   - Conversation history: sidebar with search, rename, delete, and pinned chats; shareable read-only links are optional and disabled by default.
   - Suggested starter questions and an empty state that explains what the assistant can and cannot do.
   - Scope selector: choose collection(s) and filters for a query, shown clearly in the UI.
2. **Knowledge base management**
   - Drag-and-drop multi-file upload with progress, client-side type/size validation, and per-file ingestion status (`queued -> processing -> ready | failed`) updated live; clear error messages and retry for failed jobs.
   - Document list with search, filters, status, delete (with confirmation), and metadata. Collections create/rename/delete.
3. **Admin area** (role-gated)
   - Review queue for **quarantined chunks/documents** (view flagged content safely as plain text, approve or reject), API key management, usage and cost per tenant, and basic system status (readiness of API, queue, Redis, DB).
4. **Settings**: theme (light/dark/system), language, data retention info, and account/session management.

### UX and design quality bar
- A coherent design system: design tokens (color, type scale, spacing, radius, shadow, motion) defined once and documented in `docs/UX.md`; consistent components; light and dark themes both polished.
- Clean, distraction-free chat layout (readable line length, clear message hierarchy, sticky composer, smooth auto-scroll that does not fight the user), thoughtful empty/loading/skeleton/error states, and restrained motion that respects `prefers-reduced-motion`.
- **Responsive**: excellent on mobile, tablet and desktop (mobile-first); touch-friendly targets; the citations panel becomes a bottom sheet on small screens.
- **Accessibility: WCAG 2.2 AA** as a hard requirement: full keyboard navigation and visible focus, semantic HTML/ARIA, screen-reader-friendly live regions for streaming text (announce politely, not per token), sufficient contrast, labels for every control, and no information conveyed by color alone.
- **Internationalization**: i18n from day one with **English and Swahili** (add the framework and both locale files; all strings externalized; locale-aware dates and numbers). Layout must not break with longer strings.
- Perceived performance: optimistic UI where safe, skeletons, code-splitting, image/font optimization, and a Lighthouse budget (performance and accessibility >= 90 on key pages).
- Keyboard shortcuts (e.g. new chat, focus composer, open citations) with a discoverable shortcuts dialog.

### UI-specific security (ties into Section 5A)
- Render model output as **untrusted**: sanitize Markdown/HTML (e.g. a strict allowlist sanitizer), **never use `dangerouslySetInnerHTML` with model output**, **do not render images or auto-loading remote content from model output**, open external links with `rel="noopener noreferrer"` and show the destination, and allow only allowlisted URL schemes.
- Display quarantined or untrusted document content as plain text only.
- Do not store tokens, conversations or secrets in `localStorage`; keep only non-sensitive UI preferences there. Clear client state on logout.
- Never expose `retrieval_debug` or internal scores to non-admin users.

### Backend additions required by the UI
- `conversations` and `messages` tables (tenant/user scoped, covered by RLS, included in the deletion cascade and retention policy) with endpoints: `POST/GET/PATCH/DELETE /v1/conversations`, `GET /v1/conversations/{id}/messages`.
- A documented **SSE event contract** for `/v1/query` streaming (e.g. `retrieval_started`, `citations`, `token`, `refusal`, `done`, `error`) versioned in the OpenAPI/AsyncAPI docs so the UI and API stay in sync; include `request_id` and the LangSmith run reference in `done` for admin/debug views.
- Endpoints for admin quarantine review, usage/cost summaries, and system status.

### Quality, testing and observability for the UI
- Unit/component tests (Vitest + Testing Library), end-to-end tests (**Playwright**) covering: login, upload and ingestion status, streaming chat with citations, refusal state, feedback, admin quarantine review, and mobile viewport. Run in CI against the docker-compose stack.
- Automated accessibility checks (axe) in CI and Lighthouse CI budgets; visual regression tests for key screens (optional but recommended).
- XSS tests: feed adversarial model outputs (script tags, markdown images, `javascript:` links, HTML injection) and assert nothing executes or loads.
- **Frontend observability with Grafana Faro** (real-user monitoring: JS errors, web vitals, route timings) sending to Grafana Cloud, respecting privacy (no message content, masked user IDs). Propagate the trace ID so frontend, API and LangSmith traces correlate.
- Terraform: `rag-web` service, its environment variables (BFF-only secrets marked `sensitive`), health check, and custom domain/TLS notes in the deployment guide.
- README must include **screenshots or a short GIF** of the UI (light and dark, desktop and mobile), the UI architecture diagram (browser -> Next.js BFF -> RAG API), and instructions to run the UI locally.

## 10B. Production-Readiness Standard (applies to ALL code, not only at the end)

"Production-ready" is a measurable standard here. All code delivered (backend, worker, UI, infrastructure, scripts) must meet it. A feature is not "done" until it passes this standard and the evidence is recorded in `docs/PRODUCTION_READINESS.md`.

### A. Code-level standard (every module)
- **Complete, real implementations only**: no placeholders, stubs, fake data, hardcoded demo values, commented-out code, or "happy path only" logic in production paths. Mocks and fakes live only in tests. Abstract ports may declare abstract methods; nothing else may raise `NotImplementedError`.
- **Typed, validated, documented**: full type hints (mypy strict), validated inputs at every boundary, docstrings explaining *why* for public APIs and non-obvious logic.
- **Every external call** (DB, Redis, blob store, LLM/embedding/reranker, LangSmith, Grafana export) has an explicit timeout, bounded retries (idempotent calls only) with backoff and jitter, error mapping to typed domain errors, and a defined fallback or failure behavior.
- **No unbounded resources**: bounded queues, bounded in-memory buffers, pagination everywhere, streaming for large files (never load a whole upload into memory), bounded concurrency, and limits on request size, chunk counts, and tokens.
- **Correct resource lifecycle**: connection pools and clients created once and closed on shutdown; graceful shutdown drains in-flight requests and jobs (SIGTERM handling), jobs are re-queued or safely resumable on worker crash.
- **Idempotency and exactly-once effects** where it matters (ingestion, uploads, deletes, quota accounting); safe to retry any operation.
- **Observable by construction**: every request and job emits structured logs, metrics and traces (Sections 6A, 6C); errors carry correlation IDs; no `print`, no swallowed exceptions, no sensitive data in logs.
- **Secure by default**: all Section 5/5A controls; least-privilege DB roles (the app role cannot alter schema or bypass RLS; migrations run with a separate role); no secrets in code, images or logs.
- **Configuration**: all tunables (timeouts, limits, thresholds, model names, feature flags) are validated configuration with safe defaults and documented in the README config reference; startup fails fast on invalid config.
- **Performance verified**: query plans reviewed with `EXPLAIN ANALYZE` for pgvector, FTS and tenant-filtered queries; indexes justified; N+1 queries prevented; HNSW parameters (`m`, `ef_construction`, `ef_search`) chosen from measurements and documented.

### B. Automated production gates (CI fails on violation)
- A "forbidden patterns" check in CI for production code (not tests): `NotImplementedError` outside abstract ports, `TODO`/`FIXME` without an issue link, `print(` / `console.log`, `pdb`/`breakpoint()`, `# type: ignore` or `eslint-disable` without a justification comment, `unittest.mock`/fake providers imported in `src/`, hardcoded URLs/keys/credentials (gitleaks).
- Container hardening checks: non-root user, read-only root filesystem where possible, no shell tools beyond what is needed, pinned base image digests, image scan (Trivy/Grype) with no HIGH/CRITICAL unfixed vulnerabilities, SBOM published.
- Migration check: migrations apply cleanly on an empty DB and on a populated DB, are backward compatible with the previous app version, and a rollback/forward-fix path is documented.

### C. Resilience proof (tested, not assumed)
- **Fault-injection / chaos tests** in the integration suite: Postgres unavailable, Redis (`rag-state` and `rag-cache`) unavailable, blob store errors, LLM timeouts/429/5xx, embedding provider outage, slow dependencies, worker killed mid-job, duplicate job delivery, and partial writes. Assert the documented behavior (degradation, `503` with `Retry-After`, retry, DLQ, no data corruption, no cross-tenant leakage).
- **Load, soak and spike tests** (k6/Locust) against staging: record throughput, p95/p99 latency, error rate, saturation points, and memory growth over a multi-hour soak. Compare against the NFR targets and store results under `docs/performance/`.
- **Backup and restore drill**: restore Postgres from backup into a fresh instance, verify data and pgvector indexes, and record the measured RTO/RPO. Document Redis persistence expectations for `rag-state`.
- **Deploy safety**: zero-downtime rolling deploy verified; run at least 2 API instances in production where the Render plan allows; health-gated deploys; rollback rehearsed; post-deploy smoke test script (`make smoke`).

### D. Operational readiness
- **Production Readiness Review**: `docs/PRODUCTION_READINESS.md` is a checklist with **evidence links** (test run, dashboard, doc, drill result) for every item below, ending in an explicit go/no-go decision signed off by the owner:
  - requirements and API contract approved; all FRs traced to passing tests; all NFRs verified;
  - security review done, threat model current, red-team thresholds met, secrets rotated and scoped per environment, dependency and image scans clean;
  - dashboards, alerts and runbooks exist and were exercised (at least one alert fired and handled in staging); SLOs defined; synthetic canary running;
  - backups enabled and restore drill passed; Terraform plan is clean and applied from CI; state is remote and locked;
  - capacity and cost model documented, provider spend caps and budget alerts set, kill switch tested;
  - incident response and rollback procedures documented and rehearsed; ownership/on-call and escalation path defined;
  - data retention, deletion cascade and privacy documentation complete.
- **Environments**: staging mirrors production topology (same services, smaller plans); no production data in staging; production changes only via the CI/CD pipeline.
- **Release management**: tagged semantic versions, generated changelog, versioned container images, and the running version exposed at `/version` and in logs, metrics and traces.

### E. Render-specific production notes (verify against current Render docs before relying on them)
- Choose paid plans appropriate for production for every service (free/starter tiers may sleep, lack backups or have limited resources); document the chosen plan per service and its cost in the README.
- Configure health check paths, graceful shutdown delay, autoscaling (where available), instance count, and regions consistently via Terraform; enable Postgres backups/point-in-time recovery on supported plans and set Postgres connection limits against the pool size.
- Keep services in the same region and on the private network; no public access to Postgres or Redis; restrict inbound access.

## 11. Definition of Done

- [ ] Production-Readiness Standard (Section 10B) met: forbidden-pattern and container-hardening gates pass, fault-injection tests pass, load/soak results meet NFRs, backup restore drill done, zero-downtime deploy and rollback rehearsed, and `docs/PRODUCTION_READINESS.md` is complete with evidence and an owner go/no-go.
- [ ] Phase 0 approved before coding: requirements (FR/NFR with measurable targets), API design (`openapi.yaml`, lint-clean) and architecture exist and match the implementation; traceability matrix has no untested requirement; OpenAPI breaking-change check and Schemathesis contract tests pass in CI; every NFR has a verification result (test, load test, or monitoring/SLO).
- [ ] `docker compose up` gives a working system locally; sample documents can be ingested and queried with cited answers.
- [ ] All tests pass; coverage >= 80%; mypy strict and ruff clean.
- [ ] Eval suite runs and meets thresholds; report committed under `docs/`.
- [ ] `terraform plan` is clean for staging and production; deploy guide verified step by step.
- [ ] Structured logs, traces, metrics, health checks working.
- [ ] No secrets in repo; security doc and threat model written.
- [ ] All Section 5A controls implemented and tested; `docs/AI_SECURITY.md` includes the OWASP LLM Top 10 mapping and residual risks.
- [ ] Red-team suite passes thresholds in CI; cross-tenant isolation test (RLS) passes; deletion cascade test passes.
- [ ] Architecture doc and ADRs match the final implementation.
- [ ] Section 2B principles are applied and enforced: import-linter contracts, mypy strict, ruff (incl. complexity), gitleaks and ESLint/TS strict all pass in CI; contract tests exist for every port; RFC 9457 error format used everywhere; migrations are backward compatible; `docs/GLOSSARY.md` and `docs/TECH_DEBT.md` exist.
- [ ] LangSmith tracing works end to end (full trace per request, feedback scores, masked data, outage-safe) and the LangSmith ADR (region, privacy, lock-in) is written.
- [ ] Redis: two instances provisioned by Terraform with the correct eviction policies, all ports implemented with fakes, key/TTL/version rules enforced, failure-mode tests pass, deletion cascade purges Redis.
- [ ] Grafana: metrics, logs and traces flow to Grafana Cloud via Alloy; dashboards and alert rules are provisioned by Terraform; every alert has a runbook link; synthetic canary running; local `observability` profile works.
- [ ] Every principle in Section 2A is implemented and listed in the README principles table with links to the code.
- [ ] README contains all required sections and Mermaid diagrams, renders correctly on GitHub, and the docs CI check passes.
- [ ] Web UI (Section 10A) works end to end: streaming chat with verifiable citations, document management, admin quarantine review, EN/SW i18n, light/dark, responsive, WCAG 2.2 AA (axe clean), Lighthouse budgets met, XSS tests pass, no secrets in the browser, Playwright suite green in CI, deployed on Render via Terraform.

## 12. Milestones (execute in order)

0. **Phase 0 design-first (Section 0A)**: `docs/REQUIREMENTS.md` (FR + NFR), `docs/API_DESIGN.md` + `api/openapi.yaml`, `docs/ARCHITECTURE.md` + ADRs, traceability matrix. No application code. Stop and wait for owner approval.
1. Repo scaffold, tooling, CI skeleton, config, logging, health endpoints, Dockerfile, docker-compose.
2. DB schema, migrations, repositories, auth + rate limiting.
3. Ingestion pipeline (parsers, chunking, embeddings, worker, jobs API).
4. Retrieval (dense + FTS + RRF + rerank) and generation with citations, streaming, guardrails, caching.
5. Observability (metrics, OpenTelemetry, LangSmith integration, Grafana dashboards/alerts locally), resilience (retries, circuit breaker, DLQ), load test, AND the full AI security layer (Section 5A) with the red-team suite. Security controls must exist before any real data is ingested in staging.
6. Evaluation harness and golden dataset.
7. Terraform modules, environments, remote state, deploy to staging on Render, then production.
8. Web UI/UX (Section 10A): backend additions (conversations, SSE contract, admin endpoints), BFF + auth, chat with citations, knowledge-base management, admin area, i18n, accessibility, Playwright/axe tests, Faro RUM, `docs/UX.md`. Terraform for `rag-web` is added in milestone 7 or here.
9. **Production Readiness Review** (Section 10B: chaos/load/soak tests, restore drill, rollback rehearsal, `docs/PRODUCTION_READINESS.md` go/no-go) and documentation polish (full README with all diagrams, principles table, ADR index), security review, final Definition of Done check. Note: keep the README updated at the end of EVERY milestone, not only here.

(Redis architecture, Section 6B: queue in milestone 3, caches and rate limiting in milestones 2 and 4. LangSmith, Section 6A, and Grafana instrumentation, Section 6C, in milestone 5. Provisioning Alloy and Grafana resources with Terraform in milestone 7.)

At the end of each milestone, print a short summary: what was built, what was tested, open risks, next step.
