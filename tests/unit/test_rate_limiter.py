"""Behavior tests for FR-AUTH-004 admission limits and fallback behavior."""

from __future__ import annotations

from typing import cast

import pytest
import redis.asyncio as redis_async
from redis.exceptions import RedisError

from rag.adapters.redis.rate_limiter import (
    FallbackRateLimiter,
    MemoryRateLimiter,
    RedisRateLimiter,
)
from rag.domain.ports.rate_limiter import RateLimitDecision


class UnavailableRedis:
    async def consume(
        self, tenant_id: str, key_id: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        raise RedisError("synthetic unavailable backend")


class AvailableRedis:
    def __init__(self) -> None:
        self.closed = False
        self.eval_args: tuple[object, ...] = ()

    async def eval(self, *args: object) -> int:
        self.eval_args = args
        return 2

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.closed = True


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


@pytest.mark.asyncio
async def test_req_fr_auth_004_memory_limiter_evicts_old_entries_when_bounded() -> None:
    limiter = MemoryRateLimiter(max_entries=1)

    await limiter.consume("tenant-a", "key-a", 2, 60)
    await limiter.consume("tenant-b", "key-b", 2, 60)

    assert len(limiter._entries) == 1


@pytest.mark.asyncio
async def test_req_fr_auth_004_shared_limiter_uses_atomic_tenant_key_counter() -> None:
    client = AvailableRedis()
    limiter = RedisRateLimiter(cast(redis_async.Redis, client), "test")

    decision = await limiter.consume("tenant-a", "key-a", 5, 60)
    healthy = await limiter.ping()
    await limiter.close()

    assert decision.allowed and decision.remaining == 3
    assert "rag:test:tenant-a:ratelimit:key-a:60:" in str(client.eval_args[2])
    assert healthy and client.closed


@pytest.mark.asyncio
async def test_req_fr_auth_004_limiter_uses_fallback_when_no_redis_is_configured() -> None:
    limiter = FallbackRateLimiter(None, MemoryRateLimiter(), 3, 60)

    decision = await limiter.consume("tenant-a", "key-a", 10, 60)

    assert decision.allowed and decision.limit == 3


@pytest.mark.asyncio
async def test_req_fr_auth_004_redis_url_client_has_bounded_pool_and_closes() -> None:
    limiter = RedisRateLimiter.from_url("redis://localhost:6379/0", "test")

    await limiter.close()
