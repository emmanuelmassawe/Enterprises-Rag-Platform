# Service Level Objectives

The numeric targets below are proposed, confirm with owner. No staging or production measurement is available as of M9 (2026-11-17). They are not claims of achieved service levels.

| SLI | Proposed objective | Measurement | Alert response |
|---|---|---|---|
| API availability | 99.5% monthly, excluding planned maintenance | Successful `/healthz` synthetic checks plus request success counts | Page on sustained outage; see deployment health runbook. |
| Non-LLM request latency | p95 <=300 ms at agreed baseline | `rag_http_request_duration_seconds` grouped by bounded route template | Ticket when p95 exceeds objective for 15 minutes. |
| Full answer latency | p95 <=10 s for typical queries, excluding provider outages | Request histogram with query-stage metrics after staging instrumentation; current histogram is total HTTP time | No target claim until model-pinned staging run. |
| Query first-token latency | p95 <=3 s | SSE retrieval-start to first token timestamp | Current implementation completes generation before streaming; target is at risk pending staging. |
| Ingestion reliability | No lost accepted jobs; failures end in retry or failed job state | `rag_ingestion_jobs_total`, Redis queue and DB job status | Ticket on oldest queued age / DLQ threshold after baseline. |
| Security canary | Zero tolerated leaks | `rag_ai_canary_leaks_total` | Immediate page; disable generation and follow AI incident runbook. |
| Trace export | No user request waits for LangSmith | `rag_tracing_export_failures_total` and queue behavior | Ticket on sustained export failures; trace outages do not fail query requests. |

The local `observability` Compose profile exposes Prometheus on `127.0.0.1:9090` and Grafana on `127.0.0.1:3000`. Alloy scrapes API and worker metrics every 15 seconds and accepts OTLP HTTP traces on the private Compose network. The local profile is for development only. Production contact points, silences, synthetic canaries, retention and Grafana Cloud credentials are configured in deployment, not committed here.

## Baseline load procedure

Provide a synthetic tenant, collection and API key to `make load-test` via `RAG_LOAD_BASE_URL`, `RAG_LOAD_API_KEY`, `RAG_LOAD_COLLECTION_ID`, `RAG_LOAD_REQUESTS` and `RAG_LOAD_CONCURRENCY`. Use staging only. Record the generated JSON summary with model version, environment, release and query mix in a private operations record. Do not put credentials or tenant identifiers in Git. No baseline was run in M5 because no staging target/owner credentials were supplied.
