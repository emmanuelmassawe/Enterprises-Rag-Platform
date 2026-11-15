"""FastAPI application entry point, operational routes, and runtime composition."""

from __future__ import annotations

import hmac
import re
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from rag.adapters.postgres.api_keys import PostgresApiKeyStore
from rag.adapters.redis.rate_limiter import FallbackRateLimiter, MemoryRateLimiter, RedisRateLimiter
from rag.api.routers.api_keys import router as api_keys_router
from rag.core.config import Settings, get_settings
from rag.core.errors import ProblemException
from rag.core.logging import configure_logging
from rag.db.session import Database
from rag.domain.ports.api_keys import ApiKeyStore
from rag.domain.ports.rate_limiter import RateLimiter
from rag.services.api_keys import ApiKeyService

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
REQUESTS = Counter("rag_http_requests_total", "HTTP requests", ["method", "route", "status"])
REQUEST_DURATION = Histogram(
    "rag_http_request_duration_seconds", "HTTP request duration", ["method", "route"]
)


@dataclass(slots=True)
class RuntimeComponents:
    """Adapters and services owned by one FastAPI application instance."""

    database: Database | None
    owns_database: bool
    redis_limiter: RedisRateLimiter | None
    rate_limiter: RateLimiter
    api_key_service: ApiKeyService | None


def _resolve_database(
    settings: Settings, injected: Database | None
) -> tuple[Database | None, bool]:
    if injected is not None:
        return injected, False
    if settings.database_url is None:
        return None, False
    return Database(settings.database_url.get_secret_value()), True


def _resolve_redis_limiter(settings: Settings) -> RedisRateLimiter | None:
    if settings.redis_url is None:
        return None
    return RedisRateLimiter.from_url(settings.redis_url.get_secret_value(), settings.app_env)


def _resolve_rate_limiter(
    settings: Settings, injected: RateLimiter | None, redis_limiter: RedisRateLimiter | None
) -> RateLimiter:
    if injected is not None:
        return injected
    return FallbackRateLimiter(
        redis_limiter,
        MemoryRateLimiter(),
        settings.rate_limit_memory_fallback_requests,
        settings.rate_limit_memory_fallback_window_seconds,
    )


def _resolve_api_key_service(
    database: Database | None, key_store: ApiKeyStore | None
) -> ApiKeyService | None:
    if key_store is not None:
        return ApiKeyService(key_store)
    if database is not None:
        return ApiKeyService(PostgresApiKeyStore(database))
    return None


def _runtime_components(
    settings: Settings,
    database: Database | None,
    key_store: ApiKeyStore | None,
    rate_limiter: RateLimiter | None,
) -> RuntimeComponents:
    active_database, owns_database = _resolve_database(settings, database)
    redis_limiter = _resolve_redis_limiter(settings)
    return RuntimeComponents(
        database=active_database,
        owns_database=owns_database,
        redis_limiter=redis_limiter,
        rate_limiter=_resolve_rate_limiter(settings, rate_limiter, redis_limiter),
        api_key_service=_resolve_api_key_service(active_database, key_store),
    )


async def _dependency_checks(runtime: RuntimeComponents) -> dict[str, str]:
    checks: dict[str, str] = {"api": "ok"}
    if runtime.database is None:
        checks["database"] = "not_configured"
    else:
        try:
            checks["database"] = "ok" if await runtime.database.ping() else "unavailable"
        except Exception:
            checks["database"] = "unavailable"
    if runtime.redis_limiter is None:
        checks["rate_limiter"] = "local_fallback"
    else:
        try:
            checks["rate_limiter"] = "ok" if await runtime.redis_limiter.ping() else "unavailable"
        except Exception:
            checks["rate_limiter"] = "local_fallback"
    return checks


def _request_id(request: Request) -> str:
    """Accept only bounded opaque IDs; otherwise generate one to avoid log injection."""
    candidate = request.headers.get("x-request-id", "")
    return candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else f"req_{uuid4().hex}"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach safe correlation data and record low-cardinality request metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _request_id(request)
        request.state.request_id = request_id
        logger = structlog.get_logger("http").bind(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("http_request_failed", method=request.method, path=request.url.path)
            raise
        duration = time.perf_counter() - started
        response.headers["X-Request-ID"] = request_id
        rate_limit = getattr(request.state, "rate_limit", None)
        if rate_limit is not None:
            response.headers["RateLimit-Limit"] = str(rate_limit.limit)
            response.headers["RateLimit-Remaining"] = str(rate_limit.remaining)
            response.headers["RateLimit-Reset"] = str(rate_limit.reset_at)
        route = request.scope.get("route")
        route_name = getattr(route, "path", "unmatched")
        REQUESTS.labels(request.method, route_name, str(response.status_code)).inc()
        REQUEST_DURATION.labels(request.method, route_name).observe(duration)
        logger.info(
            "http_request_completed",
            method=request.method,
            path=route_name,
            status_code=response.status_code,
            duration_seconds=round(duration, 6),
        )
        return response


def _problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 9457 response without exposing stack traces or submitted values."""
    request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        headers={"X-Request-ID": request_id, **(headers or {})},
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
            "request_id": request_id,
        },
    )


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemException)
    async def problem_error_handler(request: Request, exc: ProblemException) -> JSONResponse:
        return _problem(request, exc.status, exc.code, exc.title, exc.detail, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, _: RequestValidationError) -> JSONResponse:
        return _problem(
            request, 422, "validation_failed", "Validation failed", "Request validation failed."
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _problem(
                request, 404, "not_found", "Not found", "The requested resource was not found."
            )
        if exc.status_code == 405:
            return _problem(
                request,
                405,
                "method_not_allowed",
                "Method not allowed",
                "The method is not supported.",
            )
        return _problem(
            request,
            exc.status_code,
            "http_error",
            "Request failed",
            "The request could not be completed.",
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, _: Exception) -> JSONResponse:
        structlog.get_logger("application").exception(
            "unhandled_application_error",
            request_id=getattr(request.state, "request_id", "unknown"),
        )
        return _problem(
            request,
            500,
            "internal_error",
            "Internal server error",
            "The request could not be completed.",
        )


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    key_store: ApiKeyStore | None = None,
    rate_limiter: RateLimiter | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    """Create an app with explicit persistence and rate-limit adapters."""
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    runtime = _runtime_components(resolved, database, key_store, rate_limiter)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        try:
            yield
        finally:
            if runtime.owns_database and runtime.database is not None:
                await runtime.database.dispose()
            if runtime.redis_limiter is not None:
                await runtime.redis_limiter.close()

    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_keys_router)
    app.state.settings = resolved
    app.state.database = runtime.database
    app.state.rate_limiter = runtime.rate_limiter
    app.state.api_key_service = runtime.api_key_service
    app.state.clock = clock
    _register_error_handlers(app)

    @app.get("/healthz", tags=["Operations"], include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Report process liveness without probing dependencies."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["Operations"], include_in_schema=False)
    async def readyz() -> JSONResponse:
        """Report API, database, and shared rate-limit state health."""
        checks = await _dependency_checks(runtime)
        ready = checks["database"] == "ok" and checks["rate_limiter"] == "ok"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", "checks": checks},
        )

    @app.get("/metrics", tags=["Operations"], include_in_schema=False)
    async def metrics(request: Request) -> Response:
        """Expose metrics only when a strong bearer token is configured and presented."""
        token = resolved.metrics_scrape_token
        authorization = request.headers.get("authorization", "")
        supplied = authorization.removeprefix("Bearer ")
        if token is None or not hmac.compare_digest(supplied, token.get_secret_value()):
            return _problem(
                request,
                403,
                "permission_denied",
                "Forbidden",
                "Metrics access is not authorized.",
            )
        return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
