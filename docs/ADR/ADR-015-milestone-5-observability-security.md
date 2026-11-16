# ADR-015: M5 observability and AI security controls

- Status: Implemented for the M5 approval gate; residual production gates remain
- Date: 2026-11-16

## Context

M5 adds request correlation and low-cardinality service metrics, optional LLM tracing, worker outcome visibility, bounded retries and AI-specific detection. The repository is public. Traces and exported telemetry must never include raw questions, document text, keys, tenant names or direct user identifiers. A tracing outage cannot delay a query.

## Decisions

1. Keep Prometheus metrics behind the existing bearer-protected API endpoint. The worker exposes a private-network-only metrics listener on port 9000; Alloy scrapes both services and remote-writes to local Prometheus. Grafana dashboards and alert rules are provisioned as local files in `observability/`.
2. Add OpenTelemetry request spans with request ID, bounded route template and status only. Configure the OTLP HTTP batch exporter via `OTEL_EXPORTER_OTLP_ENDPOINT`; it writes to Alloy when enabled. No request path values, prompt content or identifiers are span attributes beyond request ID correlation.
3. Add `LLMTracer`/no-op implementations. LangSmith is opt-in. Its client hides inputs/outputs, and the adapter only queues allowlisted metadata on a bounded 512-entry queue. The export runs off the request path with a 1-second client timeout; queue overflow/failure increments `rag_tracing_export_failures_total`.
4. Security events contain bounded category/outcome, hashed tenant/key references and request ID. Query text, document text, PII and credentials are never event fields. Sensitive input behavior is configurable (`flag`, `redact`, `block`); the proposed default is `flag` until owner confirmation.
5. Prompt injection detection remains a deliberately small local heuristic, used alongside source quarantine, forced RLS, random delimiters, no tools, strict structured output, citation membership, output sanitization and a random canary. It is not treated as a model safety guarantee.
6. Terminal exhausted ingestion/deletion work remains in the tenant-scoped database job record with failed status for operator review/retry. ARQ retries are bounded and jittered. M5 emits worker success/rejection/dead-letter metrics. Redis ARQ itself does not provide a separate durable DLQ stream in this design.
7. `GENERATION_ENABLED=false` is the immediate deployment kill switch. A remote, audited per-tenant feature flag and numeric token/spend budgets await owner-defined limits and later implementation.

## Current official documentation verified (2026-11-16)

- The official LangSmith Python `Client` reference documents `api_url`, `timeout_ms`, `auto_batch_tracing`, and client-wide `hide_inputs`/`hide_outputs`/`hide_metadata`; `create_run` accepts `name`, `inputs`, `run_type`, project, timing and other run fields. The adapter uses only the metadata-only path: [Client reference](https://reference.langchain.com/python/langsmith/client/Client), [create_run reference](https://reference.langchain.com/python/langsmith/client/Client/create_run), [LangSmith tracing environment and SDK overview](https://reference.langchain.com/python/langsmith).
- Official OpenTelemetry Python exporter guidance uses `OTLPSpanExporter`, `TracerProvider` and `BatchSpanProcessor`, and recommends an OpenTelemetry Collector for production export: [OpenTelemetry exporters](https://opentelemetry.io/docs/languages/python/exporters/).
- Grafana's official Alloy docs describe `prometheus.scrape` with target lists, authorization blocks and forwarding, `prometheus.remote_write`, OTLP receiver support, and OTLP exporter timeout/queue/retry options: [Prometheus scrape](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.scrape/), [remote write](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.remote_write/), [OTLP receiver](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.receiver.otlp/), [OTLP exporter](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.otlp/).
- Official ARQ 0.28 docs describe `Retry(defer=...)`, `max_tries` and permanent failure after the retry limit. The application retains terminal failure details in its DB job record; it does not claim ARQ has a native durable DLQ: [ARQ docs](https://arq-docs.helpmanual.io/).
- AI threat mappings follow [OWASP GenAI Security Project](https://genai.owasp.org/llm-top-10/), [MITRE ATLAS](https://atlas.mitre.org/) and [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework).

## Consequences and open gates

- Platform traces can be correlated with LangSmith via request/trace identifiers, but the current adapter creates a metadata-only run rather than every nested pipeline span or feedback score.
- Grafana local dashboards can display API and worker metrics. No Grafana Cloud credentials, contact points, cloud retention, or staging synthetic checks are included.
- No raw text is intentionally exported. A serialized SDK export test and real staging outage exercise are still required before enabling LangSmith for customer traffic.
- Owner must approve the LangSmith region/retention/DPA, telemetry retention, alert contact points, sampling/tenant opt-out, PII action default, budgets and escalation owner.
- Local container image tags are version-pinned but not digest-pinned; verify current digests before production use. No Terraform is changed in M5.
