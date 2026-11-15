# ADR-004: Separate ingestion worker and queue

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

PDF parsing and embedding may exceed API request limits. Jobs need retries, idempotency, backpressure and dead-letter tracking.

## Decision

Return 202 and enqueue bounded tenant-scoped ingestion work in `rag-state`; a separately deployed worker parses, sanitizes, scans, chunks and embeds. The queue adapter/library choice (ARQ or RQ) remains for implementation evaluation against async needs and maintenance. Job states are persisted in PostgreSQL; queue messages are wake-up/control records, not the sole source of truth.

## Evidence checked

- Render [Key Value documentation](https://render.com/docs/key-value) identifies the service as Redis-compatible (new instances use Valkey 8), recommends `noeviction` for queues and `allkeys-lru` for caches, and says paid instances support persistence while free instances do not.
- The exact queue library and retry semantics are not selected by Render documentation and require a later adapter review.

## Consequences

- API stays responsive; worker concurrency can scale independently.
- Queue exhaustion must fail writes visibly; duplicate delivery must be harmless.
- Persistence reduces restart loss but does not replace durable job records or restore drills.

