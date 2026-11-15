"""Distributed rate limiting port."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Result of a single fixed-window admission decision."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: int


class RateLimiter(Protocol):
    """Tenant/key-scoped request admission interface."""

    async def consume(
        self, tenant_id: str, key_id: str, limit: int, window_seconds: int
    ) -> RateLimitDecision: ...
