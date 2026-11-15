"""Tenant-scoped atomic Redis rate limiting with conservative in-process fallback."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict

import redis.asyncio as redis
import structlog
from prometheus_client import Counter
from redis.exceptions import RedisError

from rag.domain.ports.rate_limiter import RateLimitDecision, RateLimiter

FALLBACKS = Counter("rag_rate_limit_fallback_total", "Redis rate limiter fallback activations")
_INCREMENT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


class MemoryRateLimiter:
    """Bounded per-process fallback; not a substitute for Redis across replicas."""

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[str, int] = OrderedDict()
        self._lock = asyncio.Lock()

    async def consume(
        self, tenant_id: str, key_id: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        now = int(time.time())
        bucket = now // window_seconds
        reset_at = (bucket + 1) * window_seconds
        entry_key = f"{tenant_id}:{key_id}:{bucket}"
        async with self._lock:
            count = self._entries.pop(entry_key, 0) + 1
            self._entries[entry_key] = count
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return RateLimitDecision(count <= limit, limit, max(0, limit - count), reset_at)


class RedisRateLimiter:
    """Use an atomic fixed-window counter with bounded key TTLs and socket timeouts."""

    def __init__(self, client: redis.Redis, environment: str) -> None:
        self._client = client
        self._environment = environment

    @classmethod
    def from_url(cls, url: str, environment: str) -> RedisRateLimiter:
        client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
            max_connections=32,
        )
        return cls(client, environment)

    async def consume(
        self, tenant_id: str, key_id: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        now = int(time.time())
        bucket = now // window_seconds
        reset_at = (bucket + 1) * window_seconds
        key = f"rag:{self._environment}:{tenant_id}:ratelimit:{key_id}:{window_seconds}:{bucket}"
        count_value = await self._client.eval(_INCREMENT_SCRIPT, 1, key, window_seconds + 1)
        count = int(count_value)
        return RateLimitDecision(count <= limit, limit, max(0, limit - count), reset_at)

    async def close(self) -> None:
        """Close this Redis client's owned connection pool."""
        await self._client.aclose()

    async def ping(self) -> bool:
        """Check the shared rate-limit store is reachable."""
        return bool(await self._client.ping())


class FallbackRateLimiter:
    """Degrade to a stricter local cap when shared rate-limit state is unavailable."""

    def __init__(
        self,
        primary: RateLimiter | None,
        fallback: MemoryRateLimiter,
        fallback_limit: int,
        fallback_window_seconds: int,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_limit = fallback_limit
        self._fallback_window_seconds = fallback_window_seconds

    async def consume(
        self, tenant_id: str, key_id: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        if self._primary is not None:
            try:
                return await self._primary.consume(tenant_id, key_id, limit, window_seconds)
            except (RedisError, OSError, TimeoutError):
                FALLBACKS.inc()
                structlog.get_logger("rate_limit").warning("shared_rate_limiter_unavailable")
        return await self._fallback.consume(
            tenant_id,
            key_id,
            min(limit, self._fallback_limit),
            self._fallback_window_seconds,
        )
