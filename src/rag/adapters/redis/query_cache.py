"""Versioned tenant answer cache with eviction isolated from queue state."""

from __future__ import annotations

import json
from uuid import UUID

import redis.asyncio as redis


class RedisQueryCache:
    """Store payloads in evictable Redis and epochs in the no-eviction state Redis."""

    def __init__(self, state_url: str, cache_url: str) -> None:
        options = {
            "decode_responses": True,
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "health_check_interval": 30,
            "max_connections": 32,
        }
        self._state = redis.from_url(state_url, **options)  # type: ignore[no-untyped-call]
        self._cache = redis.from_url(cache_url, **options)  # type: ignore[no-untyped-call]

    @staticmethod
    def _epoch_key(tenant_id: UUID) -> str:
        return f"rag:query-cache:epoch:{tenant_id}"

    async def get(self, tenant_id: UUID, cache_key: str) -> dict[str, object] | None:
        epoch = await self._state.get(self._epoch_key(tenant_id)) or "0"
        raw = await self._cache.get(f"rag:query-cache:{tenant_id}:{epoch}:{cache_key}")
        if raw is None:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None

    async def set(
        self, tenant_id: UUID, cache_key: str, value: dict[str, object], ttl_seconds: int
    ) -> None:
        epoch = await self._state.get(self._epoch_key(tenant_id)) or "0"
        await self._cache.set(
            f"rag:query-cache:{tenant_id}:{epoch}:{cache_key}",
            json.dumps(value, separators=(",", ":")),
            ex=ttl_seconds,
        )

    async def invalidate_tenant(self, tenant_id: UUID) -> None:
        await self._state.incr(self._epoch_key(tenant_id))

    async def close(self) -> None:
        await self._state.aclose()
        await self._cache.aclose()
