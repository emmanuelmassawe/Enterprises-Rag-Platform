"""ARQ worker lifecycle and idempotent PDF ingestion task."""

from __future__ import annotations

import asyncio
import secrets
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID

import structlog
from arq import Retry
from arq.connections import RedisSettings
from prometheus_client import Counter, start_http_server

from rag.adapters.blob.local import LocalBlobStore
from rag.adapters.blob.s3 import S3BlobStore
from rag.adapters.embeddings.gemini import EmbeddingProviderUnavailable, GeminiEmbeddings
from rag.adapters.pdf.parser import PdfRejected, parse_pdf
from rag.adapters.postgres.ingestion import PostgresIngestionRepository
from rag.adapters.redis.query_cache import RedisQueryCache
from rag.core.config import get_settings
from rag.db.session import Database
from rag.domain.ports.ingestion import BlobStore, IngestionRepository
from rag.services.ingestion import chunk_pages

worker_settings = get_settings()
JOB_OUTCOMES = Counter(
    "rag_ingestion_jobs_total", "Ingestion and deletion job outcomes", ["operation", "outcome"]
)
DEAD_LETTER_JOBS = Counter(
    "rag_dead_letter_jobs_total", "Jobs exhausted after bounded retry", ["operation"]
)


def _blob_store() -> BlobStore:
    settings = get_settings()
    if settings.blob_backend == "local":
        return LocalBlobStore(settings.blob_local_root)
    return S3BlobStore(
        bucket=settings.blob_bucket,
        region=settings.blob_region,
        endpoint_url=settings.blob_endpoint_url,
        access_key_id=settings.blob_access_key_id.get_secret_value()
        if settings.blob_access_key_id
        else None,
        secret_access_key=settings.blob_secret_access_key.get_secret_value()
        if settings.blob_secret_access_key
        else None,
    )


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    if settings.database_url is None or settings.redis_url is None:
        raise RuntimeError("DATABASE_URL and REDIS_URL are required by the ingestion worker")
    if settings.embedding_api_key is None:
        raise RuntimeError("EMBEDDING_API_KEY is required by the ingestion worker")
    database = Database(settings.database_url.get_secret_value())
    ctx["database"] = database
    ctx["repository"] = PostgresIngestionRepository(
        database, settings.embedding_model, settings.embedding_dimensions
    )
    ctx["blob_store"] = _blob_store()
    ctx["embeddings"] = GeminiEmbeddings(
        settings.embedding_api_key.get_secret_value(),
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.embedding_timeout_seconds,
    )
    if settings.cache_redis_url is not None:
        ctx["query_cache"] = RedisQueryCache(
            settings.redis_url.get_secret_value(), settings.cache_redis_url.get_secret_value()
        )
    metrics_server, metrics_thread = start_http_server(
        settings.worker_metrics_port, addr="0.0.0.0"
    )
    ctx["metrics_server"] = metrics_server
    ctx["metrics_thread"] = metrics_thread


async def shutdown(ctx: dict[str, Any]) -> None:
    metrics_server = ctx.get("metrics_server")
    if metrics_server is not None:
        metrics_server.shutdown()
        metrics_server.server_close()
        metrics_thread = ctx.get("metrics_thread")
        if metrics_thread is not None:
            metrics_thread.join(timeout=1)
    embeddings = ctx.get("embeddings")
    if embeddings is not None:
        await cast(GeminiEmbeddings, embeddings).close()
    database = ctx.get("database")
    if database is not None:
        await cast(Database, database).dispose()
    cache = ctx.get("query_cache")
    if cache is not None:
        await cast(RedisQueryCache, cache).close()


async def _invalidate_query_cache(ctx: dict[str, Any], tenant_id: UUID) -> None:
    cache = ctx.get("query_cache")
    if cache is None:
        return
    try:
        await cast(RedisQueryCache, cache).invalidate_tenant(tenant_id)
    except Exception:
        structlog.get_logger("worker").warning("query_cache_invalidation_failed")


async def process_document(
    ctx: dict[str, Any], tenant_id: str, document_id: str, job_id: str
) -> None:
    """Parse, chunk, scan, embed, and atomically index one tenant's PDF."""
    settings = get_settings()
    tenant_uuid, document_uuid, job_uuid = UUID(tenant_id), UUID(document_id), UUID(job_id)
    repository = cast(IngestionRepository, ctx["repository"])
    blob_store = cast(BlobStore, ctx["blob_store"])
    embeddings = cast(GeminiEmbeddings, ctx["embeddings"])
    document = await repository.load_for_processing(tenant_uuid, document_uuid)
    job = await repository.get_job(tenant_uuid, job_uuid)
    if (
        document is None
        or document["status"] not in {"queued", "processing"}
        or job is None
        or job["status"] not in {"queued", "processing"}
    ):
        return
    await repository.set_progress(tenant_uuid, document_uuid, job_uuid, "processing", 5)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="rag-ingest-", suffix=".pdf", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            await blob_store.download(str(document["storage_key"]), cast(BinaryIO, handle))
        await repository.set_progress(tenant_uuid, document_uuid, job_uuid, "processing", 20)
        pages = await asyncio.to_thread(parse_pdf, temporary_path, settings.blob_max_pages)
        chunks = chunk_pages(
            pages,
            max_chars=settings.ingestion_chunk_chars,
            overlap_chars=settings.ingestion_chunk_overlap_chars,
        )
        if not chunks:
            await repository.fail_processing(
                tenant_uuid, document_uuid, job_uuid, "pdf_no_extractable_text"
            )
            return
        # Quarantined text still gets a vector so an audited approval can make it
        # retrieval-eligible without reprocessing or losing the moderation decision.
        eligible = list(enumerate(chunks))
        vectors: list[list[float] | None] = [None] * len(chunks)
        for offset in range(0, len(eligible), 64):
            batch = eligible[offset : offset + 64]
            result = await embeddings.embed([chunk.content for _, chunk in batch])
            for (index, _), vector in zip(batch, result, strict=True):
                vectors[index] = vector
            progress = min(90, 30 + (offset + len(batch)) * 60 // max(1, len(eligible)))
            await repository.set_progress(
                tenant_uuid, document_uuid, job_uuid, "processing", progress
            )
        await repository.finish_processing(
            tenant_uuid, document_uuid, job_uuid, chunks, vectors, len(pages)
        )
        await _invalidate_query_cache(ctx, tenant_uuid)
        JOB_OUTCOMES.labels("ingestion", "succeeded").inc()
        structlog.get_logger("worker").info(
            "ingestion_completed",
            tenant_id=str(tenant_uuid),
            document_id=str(document_uuid),
            job_id=str(job_uuid),
            page_count=len(pages),
            chunk_count=len(chunks),
            quarantined_count=sum(chunk.quarantined for chunk in chunks),
        )
    except PdfRejected as exc:
        await repository.fail_processing(tenant_uuid, document_uuid, job_uuid, str(exc))
        JOB_OUTCOMES.labels("ingestion", "rejected").inc()
    except EmbeddingProviderUnavailable:
        attempt = int(ctx.get("job_try", 1))
        if attempt < 3:
            await repository.set_progress(tenant_uuid, document_uuid, job_uuid, "queued", 20)
            raise Retry(defer=min(30, 2**attempt + secrets.randbelow(2000) / 1000)) from None
        await repository.fail_processing(
            tenant_uuid, document_uuid, job_uuid, "embedding_provider_unavailable"
        )
        JOB_OUTCOMES.labels("ingestion", "dead_letter").inc()
        DEAD_LETTER_JOBS.labels("ingestion").inc()
    except Exception:
        attempt = int(ctx.get("job_try", 1))
        if attempt < 3:
            await repository.set_progress(tenant_uuid, document_uuid, job_uuid, "queued", 20)
            raise Retry(defer=min(30, 2**attempt + secrets.randbelow(2000) / 1000)) from None
        structlog.get_logger("worker").exception("ingestion_failed")
        await repository.fail_processing(tenant_uuid, document_uuid, job_uuid, "ingestion_failed")
        JOB_OUTCOMES.labels("ingestion", "dead_letter").inc()
        DEAD_LETTER_JOBS.labels("ingestion").inc()
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


async def process_delete(
    ctx: dict[str, Any], tenant_id: str, document_id: str, job_id: str
) -> None:
    """Purge the source object and all indexed chunks, then redact document metadata."""
    tenant_uuid, document_uuid, job_uuid = UUID(tenant_id), UUID(document_id), UUID(job_id)
    repository = cast(IngestionRepository, ctx["repository"])
    blob_store = cast(BlobStore, ctx["blob_store"])
    document = await repository.load_for_processing(tenant_uuid, document_uuid)
    job = await repository.get_job(tenant_uuid, job_uuid)
    if document is None or job is None or job["status"] != "queued":
        return
    try:
        storage_key = str(document.get("storage_key", ""))
        if storage_key:
            await blob_store.delete(storage_key)
        await repository.finish_deletion(tenant_uuid, document_uuid, job_uuid)
        await _invalidate_query_cache(ctx, tenant_uuid)
        JOB_OUTCOMES.labels("deletion", "succeeded").inc()
        structlog.get_logger("worker").info(
            "document_deletion_completed",
            tenant_id=tenant_id,
            document_id=document_id,
            job_id=job_id,
        )
    except Exception:
        attempt = int(ctx.get("job_try", 1))
        if attempt < 3:
            raise Retry(defer=min(30, 2**attempt + secrets.randbelow(2000) / 1000)) from None
        await repository.fail_deletion(tenant_uuid, job_uuid)
        JOB_OUTCOMES.labels("deletion", "dead_letter").inc()
        DEAD_LETTER_JOBS.labels("deletion").inc()


class WorkerSettings:
    """ARQ registration and bounded worker settings."""

    functions = [process_document, process_delete]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = worker_settings.ingestion_max_concurrency
    max_tries = 3
    job_timeout = 300
    keep_result = 60
    queue_name = "rag:ingestion"
    redis_settings = RedisSettings.from_dsn(
        worker_settings.redis_url.get_secret_value()
        if worker_settings.redis_url is not None
        else "redis://localhost:6379/0"
    )
