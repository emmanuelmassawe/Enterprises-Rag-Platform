"""Behavior tests for FR-AUTH-004 admission limits and fallback behavior."""

from __future__ import annotations

import pytest
from redis.exceptions import RedisError

from rag.adapters.redis.rate_limiter import FallbackRateLimiter, MemoryRateLimiter
from rag.domain.ports.rate_limiter import RateLimitDecision


class UnavailableRedis:
    async def consume(
        self, tenant_id: str, key_id: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        raise RedisError("synthetic unavailable backend")


@pytest.mark.asyncio
async def test_req_fr_auth_004_memory_limiter_separates_tenants_and_keys() -> None:
    limiter = MemoryRateLimiter()

    tenant_one_first = await limiter.consume("tenant-a", "key-a", 1, 60)
    tenant_one_second = await limiter.consume("tenant-a", "key-a", 1, 60)
    tenant_two = await limiter.consume("tenant-b", "key-a", 1, 60)
    different_key = await limiter.consume("tenant-a", "key-b", 1, 60)

    assert tenant_one_first.allowed
    assert not tenant_one_second.allowed
    assert tenant_two.allowed
    assert different_key.allowed
    assert tenant_one_second.remaining == 0


@pytest.mark.asyncio
async def test_req_fr_auth_004_redis_failure_uses_a_stricter_bounded_fallback() -> None:
    limiter = FallbackRateLimiter(
        UnavailableRedis(),
        MemoryRateLimiter(max_entries=2),
        fallback_limit=2,
        fallback_window_seconds=30,
    )

    results = [await limiter.consume("tenant-a", "key-a", 20, 60) for _ in range(3)]

    assert [result.allowed for result in results] == [True, True, False]
    assert all(result.limit == 2 for result in results)
