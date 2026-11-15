# ADR-001: PostgreSQL with pgvector and full-text search

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

V1 needs tenant-scoped transactional records, vector retrieval, keyword retrieval and durable provenance. BRIEF selects Render Postgres, pgvector HNSW and `tsvector`/GIN. A separate vector database would add another service and isolation boundary before scale is measured.

## Decision

Use PostgreSQL as the source of truth for tenant metadata, conversations, jobs metadata and indexed chunks. Enable pgvector via migration and use HNSW only after recall/latency benchmarks; pair with PostgreSQL full-text search. Enforce RLS and explicit ACL filters. Keep embedding model and vector dimension versioned; re-indexing uses a blue/green index/version before switch.

## Evidence checked

- The official [pgvector project documentation](https://github.com/pgvector/pgvector) supports exact and approximate nearest-neighbor search, HNSW and IVFFlat; it notes filtered approximate searches can return fewer rows and recommends iterative scans/partitioning for some filter patterns. It also documents `vector` dimension limits and that HNSW build/search parameters trade recall, memory and speed.
- Render's [Postgres docs](https://render.com/docs/postgresql) describe managed Postgres and supported extensions; exact pgvector availability/version and permissions must be confirmed for the chosen plan before implementation.

## Consequences

- Fewer data systems, transactional joins and one RLS enforcement point.
- ANN recall under tenant/ACL filters is not assumed; exact/iterative/partition alternatives are benchmarked.
- Embedding dimensions and model upgrades require compatibility controls and index versioning.
- RPO/RTO depend on plan and restore drill, not the presence of Postgres alone.

