# Glossary

| Term | Meaning |
|---|---|
| Tenant | An organization boundary that scopes users, collections, documents, conversations, quotas and telemetry. |
| Collection | Tenant-owned grouping of source documents used to scope retrieval. |
| Document | An uploaded PDF and its provenance, status and metadata. |
| Chunk | Bounded text segment derived from a document, with source/page metadata and embedding. |
| Embedding | Numeric vector representing text for semantic similarity retrieval. |
| Hybrid retrieval | Dense vector search plus PostgreSQL full-text search, merged by Reciprocal Rank Fusion (RRF). |
| RRF | Reciprocal Rank Fusion: merges ranked result lists using reciprocal rank contributions. |
| Citation | Verifiable reference to a retrieved chunk and its source document/page or section. |
| Groundedness | Degree to which generated claims are supported by retrieved evidence. |
| Refusal | Safe response that evidence or policy does not support an answer. |
| Quarantine | State preventing a suspicious chunk from normal retrieval until authorized review. |
| Quarantine decision | Idempotent, tenant-scoped audit record of an administrator approving or rejecting a quarantined chunk. |
| BlobStore | Port for private document object storage, implemented locally by a shared volume and in production by S3-compatible storage. |
| Ingestion job | Bounded asynchronous task that extracts, scans, chunks, embeds, and indexes a document. |
| RLS | PostgreSQL Row-Level Security policies applied using transaction-bound tenant identity. |
| BFF | Backend-for-frontend: same-origin web server that holds API credentials and proxies UI requests. |
| SSE | Server-Sent Events, one-way HTTP event stream used for incremental answer delivery. |
| Problem Details | RFC 9457 structured HTTP error response format. |
| RPO / RTO | Maximum acceptable data loss window / target time to restore service after disruption. |
| SLI / SLO | Measured service indicator / target objective over a defined period. |
| ADR | Architecture Decision Record: context, decision, consequences, and status. |
| ASR | Attack Success Rate measured on a defined red-team test set; not a general safety guarantee. |
| Idempotency key | Client token that makes retries of an unsafe request produce one logical effect. |
| Request ID / trace ID | Correlation identifier for one request / distributed operation across services. |
| LangSmith run ID | Identifier of a LangSmith trace/run, if export is enabled and succeeds. |
| `rag-state` | Redis-compatible store for queue/control/quota state using no-eviction semantics. |
| `rag-cache` | Redis-compatible cache store with eviction allowed; cache loss must not affect correctness. |
| Query cache epoch | Tenant-scoped counter in `rag-state`; advancing it makes prior tenant answer-cache keys unreachable. |

