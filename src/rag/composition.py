"""Production composition root wiring API ports to concrete adapters."""

from __future__ import annotations

from rag.adapters.postgres.api_keys import PostgresApiKeyStore
from rag.adapters.postgres.ingestion import PostgresIngestionRepository
from rag.adapters.blob.local import LocalBlobStore
from rag.adapters.blob.s3 import S3BlobStore
from rag.adapters.redis.rate_limiter import FallbackRateLimiter, MemoryRateLimiter, RedisRateLimiter
from rag.adapters.redis.ingestion_queue import ArqIngestionQueue
from rag.api.main import create_app
from rag.core.config import get_settings
from rag.db.session import Database
from rag.services.api_keys import ApiKeyService
from rag.services.ingestion import IngestionService

settings = get_settings()
database = (
    Database(settings.database_url.get_secret_value())
    if settings.database_url is not None
    else None
)
redis_limiter = (
    RedisRateLimiter.from_url(settings.redis_url.get_secret_value(), settings.app_env)
    if settings.redis_url is not None
    else None
)
ingestion_queue = (
    ArqIngestionQueue(settings.redis_url.get_secret_value())
    if settings.redis_url is not None
    else None
)
blob_store = None
if settings.blob_backend == "local":
    blob_store = LocalBlobStore(settings.blob_local_root)
elif settings.blob_backend == "s3":
    blob_store = S3BlobStore(
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
api_key_application = ApiKeyService(PostgresApiKeyStore(database)) if database is not None else None
ingestion_repository = (
    PostgresIngestionRepository(database) if database is not None else None
)
ingestion_application = (
    IngestionService(
        ingestion_repository,
        blob_store,
        ingestion_queue,
        max_upload_bytes=settings.blob_max_upload_bytes,
        max_queue_size=settings.ingestion_max_queue_size,
    )
    if ingestion_repository is not None and blob_store is not None and ingestion_queue is not None
    else None
)
rate_limiter = FallbackRateLimiter(
    redis_limiter,
    MemoryRateLimiter(),
    settings.rate_limit_memory_fallback_requests,
    settings.rate_limit_memory_fallback_window_seconds,
)


async def _cleanup() -> None:
    """Dispose pools owned by this process during graceful shutdown."""
    if database is not None:
        await database.dispose()
    if redis_limiter is not None:
        await redis_limiter.close()
    if ingestion_queue is not None:
        await ingestion_queue.close()


app = create_app(
    settings,
    api_key_application=api_key_application,
    rate_limiter=rate_limiter,
    database_probe=database,
    rate_limiter_probe=redis_limiter,
    cleanup=_cleanup,
    ingestion_service=ingestion_application,
    ingestion_repository=ingestion_repository,
    blob_store=blob_store,
    ingestion_queue=ingestion_queue,
)
