"""Production composition root wiring API ports to concrete adapters."""

from __future__ import annotations

from rag.adapters.blob.local import LocalBlobStore
from rag.adapters.blob.s3 import S3BlobStore
from rag.adapters.embeddings.gemini import GeminiEmbeddings
from rag.adapters.generation.gemini import GeminiAnswerGenerator
from rag.adapters.postgres.api_keys import PostgresApiKeyStore
from rag.adapters.postgres.ingestion import PostgresIngestionRepository
from rag.adapters.postgres.query import PostgresQueryRepository
from rag.adapters.redis.ingestion_queue import ArqIngestionQueue
from rag.adapters.redis.query_cache import RedisQueryCache
from rag.adapters.redis.rate_limiter import FallbackRateLimiter, MemoryRateLimiter, RedisRateLimiter
from rag.adapters.tracing.langsmith import LangSmithTracer
from rag.api.main import create_app
from rag.core.config import get_settings
from rag.db.session import Database
from rag.domain.ports.ingestion import BlobStore
from rag.domain.ports.tracing import LLMTracer, NoOpLLMTracer
from rag.services.api_keys import ApiKeyService
from rag.services.ingestion import HeuristicInjectionDetector, IngestionService
from rag.services.query import QueryService

settings = get_settings()
llm_tracer: LLMTracer = (
    LangSmithTracer(
        settings.langsmith_api_key.get_secret_value(),
        settings.langsmith_project,
        settings.langsmith_endpoint,
    )
    if settings.langsmith_tracing and settings.langsmith_api_key is not None
    else NoOpLLMTracer()
)
if isinstance(llm_tracer, LangSmithTracer):
    llm_tracer.start()
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
blob_store: BlobStore | None = None
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
    PostgresIngestionRepository(database, settings.embedding_model, settings.embedding_dimensions)
    if database is not None
    else None
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
query_cache = (
    RedisQueryCache(
        settings.redis_url.get_secret_value(), settings.cache_redis_url.get_secret_value()
    )
    if settings.redis_url is not None and settings.cache_redis_url is not None
    else None
)
query_embeddings = (
    GeminiEmbeddings(
        settings.embedding_api_key.get_secret_value(),
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.embedding_timeout_seconds,
    )
    if settings.embedding_api_key is not None and database is not None
    else None
)
answer_generator = (
    GeminiAnswerGenerator(
        settings.embedding_api_key.get_secret_value(),
        settings.generation_model,
        settings.generation_timeout_seconds,
        settings.generation_max_output_tokens,
        settings.generation_max_concurrency,
    )
    if settings.embedding_api_key is not None and database is not None
    else None
)
query_service = (
    QueryService(
        PostgresQueryRepository(database, settings.embedding_dimensions),
        query_embeddings,
        answer_generator,
        query_cache,
        HeuristicInjectionDetector(),
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        generation_model=settings.generation_model,
        minimum_similarity=settings.query_minimum_similarity,
        context_token_budget=settings.query_context_token_budget,
        max_output_tokens=settings.generation_max_output_tokens,
        cache_ttl_seconds=settings.query_cache_ttl_seconds,
        input_pii_action=settings.ai_input_pii_action,
        tracer=llm_tracer,
        environment=settings.app_env,
    )
    if database is not None and query_embeddings is not None and answer_generator is not None
    else None
)


async def _cleanup() -> None:
    """Dispose pools owned by this process during graceful shutdown."""
    if database is not None:
        await database.dispose()
    if redis_limiter is not None:
        await redis_limiter.close()
    if ingestion_queue is not None:
        await ingestion_queue.close()
    if query_embeddings is not None:
        await query_embeddings.close()
    if answer_generator is not None:
        await answer_generator.close()
    if query_cache is not None:
        await query_cache.close()
    await llm_tracer.close()


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
    query_service=query_service,
    query_cache=query_cache,
)
