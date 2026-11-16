"""Application port for optional LLM-specific trace export."""

from __future__ import annotations

from typing import Protocol


class LLMTracer(Protocol):
    """Accept content-free LLM run metadata without blocking the user request."""

    def record_run(self, metadata: dict[str, str | int | float | bool]) -> None: ...


class NoOpLLMTracer:
    """Safe default when external tracing is disabled."""

    def record_run(self, metadata: dict[str, str | int | float | bool]) -> None:
        return None

    async def close(self) -> None:
        return None
