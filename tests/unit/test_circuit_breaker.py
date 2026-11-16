from __future__ import annotations

import pytest

from rag.services.resilience import AsyncCircuitBreaker, CircuitOpen


@pytest.mark.asyncio
async def test_breaker_opens_after_failures_and_recovers_after_one_probe() -> None:
    now = 100.0
    breaker = AsyncCircuitBreaker(failure_threshold=2, cooldown_seconds=5, clock=lambda: now)

    async def fail() -> str:
        raise OSError("provider down")

    with pytest.raises(OSError):
        await breaker.call(fail)
    with pytest.raises(OSError):
        await breaker.call(fail)
    with pytest.raises(CircuitOpen):
        await breaker.call(lambda: _value("not called"))

    now += 6
    assert await breaker.call(lambda: _value("recovered")) == "recovered"


async def _value(value: str) -> str:
    return value
