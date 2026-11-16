"""Privacy-safe OpenTelemetry setup for platform request spans."""

from __future__ import annotations

import threading

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_LOCK = threading.Lock()
_CONFIGURED = False


def configure_tracing(endpoint: str | None, service_name: str) -> None:
    """Configure a bounded batch exporter once; requests remain unaffected by outages."""
    global _CONFIGURED
    with _LOCK:
        if _CONFIGURED:
            return
        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name}),
            shutdown_on_exit=False,
        )
        if endpoint:
            exporter = OTLPSpanExporter(endpoint=endpoint, timeout=1)
            provider.add_span_processor(
                BatchSpanProcessor(
                    exporter,
                    max_queue_size=512,
                    max_export_batch_size=64,
                    schedule_delay_millis=1_000,
                    export_timeout_millis=1_000,
                )
            )
        trace.set_tracer_provider(provider)
        _CONFIGURED = True


def current_trace_id() -> str | None:
    """Return the active trace ID as an opaque hexadecimal correlation value."""
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else None
