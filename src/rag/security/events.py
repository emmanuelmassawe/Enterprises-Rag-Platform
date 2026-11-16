"""Redacted security event reporting and bounded-cardinality metrics."""

from __future__ import annotations

import hashlib

import structlog
from prometheus_client import Counter

SECURITY_EVENTS = Counter(
    "rag_ai_security_events_total",
    "AI security events by bounded category and outcome",
    ["category", "outcome"],
)
CANARY_LEAKS = Counter("rag_ai_canary_leaks_total", "Detected model canary disclosures")


def emit_security_event(
    category: str, outcome: str, *, tenant_id: str, key_id: str, request_id: str
) -> None:
    """Log identifiers as keyed-free digests; never accept raw user/model content."""
    SECURITY_EVENTS.labels(category, outcome).inc()
    structlog.get_logger("security").warning(
        "ai_security_event",
        category=category,
        outcome=outcome,
        tenant_ref=hashlib.sha256(tenant_id.encode()).hexdigest()[:16],
        key_ref=hashlib.sha256(key_id.encode()).hexdigest()[:16],
        request_id=request_id,
    )


def emit_canary_leak(*, tenant_id: str, key_id: str, request_id: str) -> None:
    CANARY_LEAKS.inc()
    emit_security_event(
        "canary_leak", "blocked", tenant_id=tenant_id, key_id=key_id, request_id=request_id
    )
