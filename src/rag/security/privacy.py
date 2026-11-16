"""Small, deterministic privacy filters for telemetry and model boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
API_SECRET = re.compile(
    r"(?i)\b(?:api[_ -]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}"
)


def redact_text(value: str) -> str:
    """Mask common direct identifiers and credential-shaped strings."""
    value = EMAIL.sub("[REDACTED_EMAIL]", value)
    value = BEARER.sub("Bearer [REDACTED]", value)
    return API_SECRET.sub("[REDACTED_SECRET]", value)


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact all strings before they are sent to an external tracer."""
    return {str(key): redact_value(item) for key, item in value.items()}


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value


def contains_sensitive(value: str) -> bool:
    """Return whether input contains a supported PII or credential pattern."""
    return redact_text(value) != value
