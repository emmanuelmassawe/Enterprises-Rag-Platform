# ADR-011: OpenTelemetry, Grafana Cloud and LangSmith

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

BRIEF assigns platform health to Grafana and model-specific traces/evaluation/feedback to LangSmith. Privacy requires redaction and vendor outages cannot delay user responses.

## Decision

Instrument API and worker with OpenTelemetry and structured JSON logs; use Alloy as the telemetry collector and Grafana Cloud for platform metrics/logs/traces/dashboards/alerts. Use LangSmith Cloud behind an `LLMTracer` port for redacted LLM traces and evaluation workflows. Export asynchronously with bounded queues/timeouts. A no-op tracer and OTel provider preserve portability. Browser Faro telemetry excludes user messages and masks user identifiers. Select LangSmith region only after owner privacy review; trace retention/deletion remains an open question.

## Evidence checked (checked 2026-11-15)

- Grafana official [Grafana Cloud docs](https://grafana.com/docs/grafana-cloud/learn-and-build/get-started/learn/) state Free tier is available with lower ingestion limits, shorter retention and community support; supports ingestion of metrics, logs, traces and profiles through Alloy/OTLP and other paths. Current [pricing](https://grafana.com/pricing/) must be rechecked when estimating budget.
- Grafana official [Alloy docs](https://grafana.com/docs/alloy/latest/) describe Alloy as the OpenTelemetry collector distribution for collecting/processing/exporting telemetry. Exact components and config are implementation-specific.
- LangChain official [LangSmith docs](https://docs.langchain.com/langsmith/observability) and [environment variables reference](https://docs.langchain.com/langsmith/env-var) must be checked immediately before coding for current SDK/env names. Current search surfaced LangSmith docs describing tracing modes and cloud/self-hosted options; privacy/region/retention configuration for the chosen plan is not verified here and remains an explicit approval question.
- Do not infer that SDK hooks guarantee redaction. Verify actual SDK semantics and test serialized export payloads before enabling external traces.

## Consequences

- Separates model-level debugging from platform SLO monitoring while linking by opaque request/trace IDs.
- Adds vendor and ingestion costs; free tier limits and retention may not meet production needs.
- External trace deletion and no-raw-text guarantees require explicit adapter implementation, payload tests, and vendor policy review.

