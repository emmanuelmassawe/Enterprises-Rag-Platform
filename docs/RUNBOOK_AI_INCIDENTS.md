# AI Security Incident Runbook

This is a local operator procedure. Do not place customer text, secrets, or production identifiers in tickets or public repository notes.

## Canary leak or suspected prompt/data disclosure

1. Treat any `rag_ai_canary_leaks_total` increase or credible disclosure report as a security incident. Capture UTC time, request ID, trace ID, release and metric event; do not copy the answer or source text into logs or chat.
2. Set `GENERATION_ENABLED=false` and deploy/restart the affected environment. If retrieval is also suspect, block `/v1/query` at the BFF/API gateway until an operator verifies tenant isolation.
3. Revoke and rotate the affected Gemini, LangSmith, Grafana and application credentials through their secret managers. Never paste the replacement credentials into this repository.
4. Identify the tenant and request using request ID and hashed tenant reference. Preserve only the minimum redacted metadata required by incident policy.
5. If a source may be poisoned, quarantine the document/chunks using the tenant-scoped admin review operation. Remove or correct the source, increment the tenant cache epoch, and verify it no longer appears in eligible retrieval.
6. Purge tenant query cache. For deletion requests, follow the data deletion procedure across DB, blob, Redis and provider traces; confirm trace deletion capability with the owner-approved LangSmith account before claiming completion.
7. Review auth, RLS, request-scoped logs, provider traces and audit rows for the incident window. Look for cross-tenant attempts, rate/cost anomalies and repeated prompt probes without exporting raw content.
8. Notify the named incident owner through the approved private escalation channel, preserve evidence, record impact and complete legal/privacy notification decisions with the owner.
9. Keep generation disabled until the incident owner approves a tested fix. Run the red-team suite, RLS adversarial checks, privacy export tests and regression tests before re-enabling.

## Queue, provider or tracing incident

- Provider outage: verify circuit breaker and provider timeout metrics. Query failures should be bounded; ingestion retries use capped attempts with jitter and terminal failed jobs are retained as failed DB job records for operator retry.
- LangSmith unavailable: answers continue without waiting for the exporter; check `rag_tracing_export_failures_total`. Do not increase queue size without memory review.
- Grafana/Alloy unavailable: app requests continue; restore scrape/export path and confirm fresh samples. Missing-scrape alerts and cloud contact points require the deployment operator's configuration.

## Escalation gaps

The owner has not named an on-call person, escalation channel, support hours, or legal/privacy notification contact. These must be set before staging receives real data.
