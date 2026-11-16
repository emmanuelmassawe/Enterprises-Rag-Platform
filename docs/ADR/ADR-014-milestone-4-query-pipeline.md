# ADR-014: Milestone 4 query pipeline

- Status: Proposed for owner review at the Milestone 4 gate
- Date: 2026-11-16
- Decision owners: Platform owner and engineering

## Context

Milestone 4 connects tenant-scoped hybrid search to fixed, no-tool answer generation. The approved API contract requires a versioned SSE sequence with citations before answer text, exact citation membership, and a safe refusal for unsupported output. This repository's M2 schema uses a dimension-flexible pgvector column and English PostgreSQL full-text index.

## Decisions

1. Query embeddings reuse the configured Gemini embedding model and key. Dense cosine distance and English full-text rank are fused with RRF. Only ready documents and clear or approved chunks are eligible. Every query runs inside a tenant-bound RLS transaction and also filters by tenant and selected collection IDs.
2. Generation uses an async Google Gen AI SDK port and Pydantic structured output. `gemini-3.8-flash` is a proposed default because Google's current stable model page documents this ID and structured-output support; the owner must confirm the model, API account location, data handling terms, and spend limits before production. No tools, grounding or external search are configured. The application validates schema, claim text, citation membership, sanitization and refusal outcomes independently of provider-side JSON formatting.
3. To meet the contract ordering, generation completes and claims are validated before the server emits citations and token-shaped SSE events. This keeps invalid claims out of the stream, but the emitted chunks are transport chunks rather than provider-token streaming. This may miss the proposed p95 time-to-first-token objective and must be measured against the staging latency target before release.
4. RRF is implemented. Reranking is deferred because no approved model or evaluation evidence is available to justify its latency and cost. ADR-003 remains the design authority; enabling a reranker requires measured evaluation and a new owner-approved decision.
5. Redis response caching is tenant-scoped, short-lived, versioned by prompt/model/config and tenant epoch. Payloads live in the evictable cache service; epoch counters live in the no-eviction state service. Cache hits re-read citation eligibility from PostgreSQL. Ingestion completion, document deletion and quarantine decisions increment the tenant epoch. Cache read/write errors fail open.
6. A new nullable `query_logs.request_id` field provides request correlation without requiring a destructive M2 table change. The audit row is written before a successful response is returned; audit failure fails the query closed with a retryable service error.
7. Query embedding and answer generation each use an in-process asynchronous circuit breaker: five consecutive provider failures open the circuit for 30 seconds, after which a single probe may test recovery. Calls use explicit provider timeouts; no application retry is added because the provider operations are externally billed and automatic retry semantics must be measured and bounded.

## Consequences

- Query requests require the Google API key, database and matching embedding configuration. Local development without these dependencies returns a stable 503 from `/v1/query`.
- `conversation_id` is accepted for API compatibility but is not used for history or persistence in M4; M8 owns the conversation endpoints and UI behavior.
- Retrieval uses exact pgvector cosine ordering without an ANN index at this milestone. A dimension-specific index is a later measured migration.
- Full structured generation before any answer text gives strong citation ordering but increases TTFT. Latency and recall thresholds need a model-pinned staging evaluation; no performance claim is made here.
- Cache invalidation is tenant-wide and safe but may reduce hit ratio during ingestion-heavy periods. Cache remains an optimization and never an authorization boundary.
- Current official references checked 2026-11-16: [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models), [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output), [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/), [pgvector project documentation](https://github.com/pgvector/pgvector), [Redis eviction policies](https://redis.io/docs/latest/reference/eviction/), [Render Terraform provider guidance](https://render.com/docs/terraform-provider), [Render provider registry](https://registry.terraform.io/providers/render-oss/render/latest), [Grafana Alloy OpenTelemetry](https://grafana.com/docs/alloy/latest/introduction/otel_alloy/), and [LangSmith observability overview](https://www.langchain.com/langsmith/observability). Render, Terraform, LangSmith and Grafana are not activated or changed in M4; their M7/M5 decisions remain governed by ADR-010/011.

## Verification required before production

- Contract tests for tenant-isolated hybrid retrieval, generation validation, citation membership, SSE terminal ordering and cache invalidation.
- Staging evaluation of RRF recall, refusal accuracy, citation support, p95 non-LLM latency, p95 time-to-first-token and full answer latency.
- Owner confirmation of proposed generation model and query/cache defaults.
