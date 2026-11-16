"""Bounded, content-free asynchronous LangSmith run exporter."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import structlog
from langsmith import Client
from prometheus_client import Counter

from rag.domain.ports.tracing import LLMTracer

EXPORT_FAILURES = Counter(
    "rag_tracing_export_failures_total", "LangSmith runs dropped or failed during export"
)


class LangSmithTracer(LLMTracer):
    """Export bounded metadata from a worker queue; raw prompts and outputs are excluded."""

    def __init__(
        self,
        api_key: str,
        project: str,
        endpoint: str | None = None,
        sample_rate: float = 1.0,
    ) -> None:
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
        self._sample_rate = sample_rate
        self._queue: asyncio.Queue[dict[str, str | int | float | bool]] = asyncio.Queue(512)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="langsmith-trace-export")

    def record_run(self, metadata: dict[str, str | int | float | bool]) -> None:
        safe_metadata = {
            key: value
            for key, value in metadata.items()
            if key
            in {
                "request_id",
                "trace_id",
                "environment",
                "release",
                "model",
                "embedding_model",
                "prompt_version",
                "input_tokens",
                "output_tokens",
                "duration_ms",
                "outcome",
                "tenant_ref",
                "finish_reason",
                "cost_estimate_available",
                "retrieved_chunks",
                "collection_refs",
            }
        }
        if secrets.randbelow(1_000_000) >= int(self._sample_rate * 1_000_000):
            return
        try:
            self._queue.put_nowait(safe_metadata)
            trace_ref = str(
                safe_metadata.get("trace_id", safe_metadata.get("request_id", "unknown"))
            )
            run_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"enterprise-rag:{trace_ref}",
            )
            structlog.get_logger("tracing").info(
                "langsmith_trace_queued",
                request_id=safe_metadata.get("request_id", "unknown"),
                langsmith_run_id=str(run_id),
            )
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
        start_time = now - timedelta(milliseconds=int(metadata["duration_ms"]))
        request_ref = str(metadata.get("trace_id", metadata.get("request_id", "unknown")))
        root_id = uuid.uuid5(uuid.NAMESPACE_URL, f"enterprise-rag:{request_ref}")
        self._client.create_run(
            id=root_id,
            name="rag.query",
            run_type="chain",
            inputs={},
            outputs={},
            project_name=self._project,
            start_time=start_time,
            end_time=now,
            extra={
                "metadata": {
                    key: metadata[key]
                    for key in (
                        "request_id",
                        "trace_id",
                        "tenant_ref",
                        "environment",
                        "release",
                        "outcome",
                        "collection_refs",
                    )
                    if key in metadata
                }
            },
        )
        stages = (
            ("retrieval", "retriever"),
            ("generation", "llm"),
            ("guardrails", "chain"),
            ("citation_verification", "parser"),
        )
        for stage, run_type in stages:
            stage_id = uuid.uuid5(root_id, stage)
            stage_metadata = {
                "stage": stage,
                "environment": metadata["environment"],
                "release": metadata["release"],
                "tenant_ref": metadata["tenant_ref"],
                "duration_ms": metadata["duration_ms"],
            }
            if stage == "generation":
                stage_metadata.update(
                    {
                        "model": metadata["model"],
                        "prompt_version": metadata["prompt_version"],
                        "input_tokens": metadata["input_tokens"],
                        "output_tokens": metadata["output_tokens"],
                        "finish_reason": metadata["finish_reason"],
                        "duration_ms": metadata["duration_ms"],
                        "cost_estimate_available": metadata["cost_estimate_available"],
                    }
                )
            if stage == "retrieval":
                stage_metadata["retrieved_chunks"] = metadata["retrieved_chunks"]
                stage_metadata["embedding_model"] = metadata["embedding_model"]
            self._client.create_run(
                id=stage_id,
                parent_run_id=root_id,
                name=f"rag.{stage}",
                run_type=cast(
                    Literal["tool", "chain", "llm", "retriever", "embedding", "prompt", "parser"],
                    run_type,
                ),
                inputs={},
                outputs={},
                project_name=self._project,
                start_time=start_time,
                end_time=now,
                extra={"metadata": stage_metadata},
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
        with suppress(asyncio.CancelledError):
            await task
        self._task = None
        try:
            await asyncio.wait_for(asyncio.to_thread(self._client.flush), timeout=1.25)
        except Exception:
            EXPORT_FAILURES.inc()
            structlog.get_logger("tracing").warning("langsmith_flush_failed")
