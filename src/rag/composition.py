"""Production composition root wiring API ports to concrete adapters."""

from __future__ import annotations

from rag.adapters.postgres.api_keys import PostgresApiKeyStore
from rag.adapters.redis.rate_limiter import FallbackRateLimiter, MemoryRateLimiter, RedisRateLimiter
from rag.api.main import create_app
from rag.core.config import get_settings
from rag.db.session import Database
from rag.services.api_keys import ApiKeyService

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
api_key_application = ApiKeyService(PostgresApiKeyStore(database)) if database is not None else None
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


app = create_app(
    settings,
    api_key_application=api_key_application,
    rate_limiter=rate_limiter,
    database_probe=database,
    rate_limiter_probe=redis_limiter,
    cleanup=_cleanup,
)
