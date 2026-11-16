from __future__ import annotations

from uuid import uuid4

import pytest

from rag.adapters.redis import query_cache
from rag.adapters.redis.query_cache import RedisQueryCache


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.closed = False

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value
        self.ttls[key] = ex

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_cache_uses_tenant_epoch_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    state, cache = _Redis(), _Redis()
    clients = iter((state, cache))
    monkeypatch.setattr(query_cache.redis, "from_url", lambda *args, **kwargs: next(clients))
    adapter = RedisQueryCache("redis://state", "redis://cache")
    tenant_a, tenant_b = uuid4(), uuid4()

    await adapter.set(tenant_a, "prompt:digest", {"answer": "a"}, 45)
    assert await adapter.get(tenant_a, "prompt:digest") == {"answer": "a"}
    assert await adapter.get(tenant_b, "prompt:digest") is None
    assert list(cache.ttls.values()) == [45]
    await adapter.invalidate_tenant(tenant_a)
    assert await adapter.get(tenant_a, "prompt:digest") is None
    await adapter.close()
    assert state.closed and cache.closed
