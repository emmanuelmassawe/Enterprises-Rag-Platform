"""Small asynchronous circuit breaker for bounded external provider calls."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class CircuitOpen(RuntimeError):
    """The provider circuit is open or another half-open probe is in flight."""


class AsyncCircuitBreaker:
    """Open after consecutive failures, permit one cooldown probe, and reset on success."""

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._open_until = 0.0
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        probe = False
        async with self._lock:
            now = self._clock()
            if self._open_until and now < self._open_until:
                raise CircuitOpen("provider circuit is open")
            if self._open_until:
                if self._probe_in_flight:
                    raise CircuitOpen("provider recovery probe is in flight")
                self._probe_in_flight = True
                probe = True
        try:
            result = await operation()
        except Exception:
            async with self._lock:
                self._failures += 1
                self._probe_in_flight = False
                if probe or self._failures >= self._threshold:
                    self._open_until = self._clock() + self._cooldown
            raise
        async with self._lock:
            self._failures = 0
            self._open_until = 0.0
            self._probe_in_flight = False
        return result
