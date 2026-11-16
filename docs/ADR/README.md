# Architecture Decision Records

Status: ADR-001 through ADR-011 were approved with Phase 0. ADR-012 records Milestone 2, ADR-013 Milestone 3, ADR-014 Milestone 4, ADR-015 the Milestone 5 implementation, and ADR-016 the Milestone 6 evaluation approach.

| ADR | Decision |
|---|---|
| [ADR-001](ADR-001-postgres-pgvector.md) | Postgres + pgvector and FTS as primary structured/vector store. |
| [ADR-002](ADR-002-rest-sse.md) | REST/HTTPS with SSE for query streaming; asynchronous ingestion jobs. |
| [ADR-003](ADR-003-hybrid-retrieval.md) | Hybrid dense + FTS retrieval, RRF and evaluation-gated optional reranking. |
| [ADR-004](ADR-004-worker-queue.md) | Independent worker and `rag-state` queue for ingestion. |
| [ADR-005](ADR-005-blob-upload.md) | Private S3-compatible blob port; bounded non-resumable PDF upload for v1. |
| [ADR-006](ADR-006-redis-split.md) | Two Render Key Value stores separated by state/cache policy. |
| [ADR-007](ADR-007-tenant-rls.md) | PostgreSQL RLS plus application tenant filters and transaction context. |
| [ADR-008](ADR-008-gemini-guarded-rag.md) | Gemini provider preference behind ports; fixed no-tool guarded RAG pipeline. |
| [ADR-009](ADR-009-web-bff.md) | Next.js BFF with Google sign-in and secure same-origin session. |
| [ADR-010](ADR-010-render-terraform.md) | Render deployment managed by official Terraform provider. |
| [ADR-011](ADR-011-observability.md) | OTel/Alloy/Grafana Cloud for platform telemetry and LangSmith for redacted LLM traces. |
| [ADR-012](ADR-012-milestone-2-persistence-and-auth.md) | Milestone 2 implementation choices for async persistence, forced RLS, hashed API keys, and Redis rate limiting. |
| [ADR-013](ADR-013-milestone-3-ingestion.md) | Bounded PDF ingestion, private blob storage, ARQ jobs, Gemini embeddings, and audited quarantine review. |
| [ADR-014](ADR-014-milestone-4-query-pipeline.md) | Tenant-scoped hybrid retrieval, structured Gemini generation, citation checks, SSE and versioned cache. |
| [ADR-015](ADR-015-milestone-5-observability-security.md) | OpenTelemetry, metadata-only LangSmith runs, Grafana local metrics, worker failure accounting and AI security controls. |
| [ADR-016](ADR-016-milestone-6-evaluation-harness.md) | Versioned synthetic evaluation harness, metrics, LLM judge and owner-approved threshold gates. |

