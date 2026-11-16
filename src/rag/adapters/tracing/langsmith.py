"""Bounded, content-free asynchronous LangSmith run exporter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog
from langsmith import Client
from prometheus_client import Counter

from rag.domain.ports.tracing import LLMTracer

EXPORT_FAILURES = Counter(
    "rag_tracing_export_failures_total", "LangSmith runs dropped or failed during export"
)


class LangSmithTracer(LLMTracer):
    """Export bounded metadata from a worker queue; raw prompts and outputs are excluded."""

    def __init__(self, api_key: str, project: str, endpoint: str | None = None) -> None:
        self._client = Client(
            api_key=api_key,
            api_url=endpoint,
            hide_inputs=True,
            hide_outputs=True,
            hide_metadata=False,
            auto_batch_tracing=True,
            timeout_ms=1_000,
        )
        self._project = project
        self._queue: asyncio.Queue[dict[str, str | int | float | bool]] = asyncio.Queue(512)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="langsmith-trace-export")

    def record_run(self, metadata: dict[str, str | int | float | bool]) -> None:
        safe_metadata = {
            key: value
            for key, value in metadata.items()
            if key in {
                "request_id",
                "trace_id",
                "environment",
                "release",
                "model",
                "prompt_version",
                "input_tokens",
                "output_tokens",
                "duration_ms",
                "outcome",
                "tenant_ref",
            }
        }
        try:
            self._queue.put_nowait(safe_metadata)
        except asyncio.QueueFull:
            EXPORT_FAILURES.inc()
            structlog.get_logger("tracing").warning("langsmith_export_queue_full")

    async def _run(self) -> None:
        while True:
            metadata = await self._queue.get()
            try:
                await asyncio.to_thread(self._export, metadata)
            except Exception:
                EXPORT_FAILURES.inc()
                structlog.get_logger("tracing").warning("langsmith_export_failed")
            finally:
                self._queue.task_done()

    def _export(self, metadata: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        self._client.create_run(
            name="rag.query",
            run_type="chain",
            inputs={},
            outputs={},
            project_name=self._project,
            start_time=now,
            end_time=now,
            extra={"metadata": metadata},
        )

    async def close(self, timeout_seconds: float = 0.25) -> None:
        task = self._task
        if task is None:
            return
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout_seconds)
        except TimeoutError:
            EXPORT_FAILURES.inc(self._queue.qsize())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._task = None
        await asyncio.to_thread(self._client.flush)
