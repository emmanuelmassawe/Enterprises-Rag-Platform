"""ARQ-backed Redis queue with stable job IDs and short connection timeouts."""

from __future__ import annotations

from uuid import UUID

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings


class ArqIngestionQueue:
    """Enqueue only opaque resource IDs; document contents stay in private storage."""

    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def _connection(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(self._settings, default_queue_name="rag:ingestion")
        return self._pool

    async def enqueue(self, tenant_id: UUID, document_id: UUID, job_id: UUID) -> None:
        pool = await self._connection()
        await pool.enqueue_job(
            "process_document",
            str(tenant_id),
            str(document_id),
            str(job_id),
            _job_id=f"ingest:{job_id}",
            _queue_name="rag:ingestion",
        )

    async def ping(self) -> bool:
        return bool(await (await self._connection()).ping())

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
