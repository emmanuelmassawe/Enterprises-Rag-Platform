# ADR-012: Milestone 2 persistence, credential and rate-limit implementation

- Status: proposed for owner review at Milestone 2 completion
- Date: 2026-11-15
- Context: implement the already-approved persistence and isolation decisions in ADR-001 and ADR-007, and authentication/rate limiting requirements, without committing to an embedding dimension that remains open.

## Decision

- Use SQLAlchemy's async engine with `asyncpg`, Alembic-managed schema migrations, and the `pgvector` SQLAlchemy type. Keep the embedding column un-sized and un-indexed until the owner selects an embedding model and dimension. PostgreSQL uses a stored English `tsvector`, a GIN index, and JSONB metadata index. PostgreSQL rejects an HNSW vector index without a declared dimension; add the cosine index with a new approved migration after the model decision and measured query plans.
- Create tenant-bound DB transactions that set `app.tenant_id` transaction-locally. The schema migration enables and forces RLS for each tenant-bearing table, applies matching `USING` and `WITH CHECK` predicates, and grants table operations to `rag_runtime`. Migrations use a separate `rag_migrator` role. The runtime role is not a superuser and does not have `BYPASSRLS`.
- Store API-key hashes only. Return a new raw credential only in its issuance response. Key creation requires a tenant-scoped idempotency key; because raw credentials cannot be recovered after creation, a repeated request returns a stable `409 idempotency_conflict` instead of reconstructing the original response. Expired idempotency rows are removed in bounded batches during new key issuance.
- Use Redis `INCR` plus expiry in one Lua operation for tenant/key-scoped fixed-window rate limits. On Redis failure, apply a bounded, stricter in-process limit and increment `rag_rate_limit_fallback_total`. The fallback is per process and therefore cannot guarantee aggregate limits across replicas; readiness reports the shared limiter as fallback/unavailable.
- Local Compose uses separate internal-only `state` (`noeviction`) and `cache` (`allkeys-lru`, 128 MiB development cap) Redis services, matching ADR-006. The cache service is present before the cache adapter is introduced. Local Postgres uses a non-published port and trusted container-network access for development only; production must use Render's private authenticated database URL and separate migration/runtime credentials.

## Consequences

- No dimension-specific vector index is declared until the embedding model decision is approved. Query-plan and HNSW tuning must be measured before production readiness. Initial migration verification found PostgreSQL rejects an HNSW index on an unconstrained vector column, so the index was removed rather than guessing a dimension.
- Local database bootstrap/first-tenant provisioning is an operational prerequisite for the admin API and must use the dedicated migration/provisioning credentials.
- Same-key API-key retries cannot return a second copy of the one-time secret. Clients must securely persist the original response and must not retry after losing it without a new idempotency key and owner reconciliation.
- Process-local rate limiting is a controlled degradation mode only; it weakens global enforcement during Redis outages. Alerting and rate-limit policy remain required in later observability work.
- Old idempotency records are pruned only on issuance activity, in batches of at most 100 per tenant per issuance; a dedicated scheduled cleanup may be added if measured row volume warrants it.

## NFR mapping

| NFR | Architectural decision |
|---|---|
| NFR-SEC-001, NFR-SEC-002 | ADR-007 RLS plus tenant predicates; runtime DB role cannot bypass RLS. |
| NFR-SEC-003 | API-key random secret is returned once; only SHA-256 digest is stored; constant-time digest comparison. |
| NFR-REL-001 | Redis atomic window counters plus stricter bounded fallback and health reporting. |
| NFR-PERF-001 | Bounded DB pool, query indexes, and no guessed vector dimension; query-plan tuning remains a release gate. |
| NFR-OPS-001 | Async SQLAlchemy, Redis health probes, Prometheus fallback counter, and migration/runtime role separation. |

## Official documentation checked

Checked 2026-11-15:

- SQLAlchemy asyncio engine and session patterns: [Asyncio Extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html).
- Alembic async migration recipes: [Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html).
- PostgreSQL row security, policy behavior, and owner/bypass rules: [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- PostgreSQL transaction-local settings using `set_config`: [System Administration Functions](https://www.postgresql.org/docs/18/functions-admin.html).
- pgvector extension, vector type, HNSW index and operator classes: [pgvector](https://github.com/pgvector/pgvector).
- pgvector SQLAlchemy integration: [pgvector-python](https://github.com/pgvector/pgvector-python).
- redis-py async client and lifecycle: [Asyncio Examples](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html).
- Render PostgreSQL extension support and enabling pgvector: [PostgreSQL Extensions](https://render.com/docs/postgresql-extensions).
