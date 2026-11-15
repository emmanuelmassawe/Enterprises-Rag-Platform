"""FastAPI application entry point and health/metrics contract."""

import hmac
import re
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from rag.core.config import Settings, get_settings
from rag.core.logging import configure_logging

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
REQUESTS = Counter("rag_http_requests_total", "HTTP requests", ["method", "route", "status"])
REQUEST_DURATION = Histogram("rag_http_request_duration_seconds", "HTTP request duration", ["method", "route"])


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


def _problem(request: Request, status: int, code: str, title: str, detail: str) -> JSONResponse:
    """Build an RFC 9457 response without exposing stack traces or submitted values."""
    request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        headers={"X-Request-ID": request_id},
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
            "request_id": request_id,
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an app instance, allowing isolated settings in tests and deployments."""
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        yield

    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, _: RequestValidationError) -> JSONResponse:
        return _problem(request, 422, "validation_failed", "Validation failed", "Request validation failed.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _problem(request, 404, "not_found", "Not found", "The requested resource was not found.")
        if exc.status_code == 405:
            return _problem(request, 405, "method_not_allowed", "Method not allowed", "The method is not supported.")
        return _problem(request, exc.status_code, "http_error", "Request failed", "The request could not be completed.")

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, _: Exception) -> JSONResponse:
        structlog.get_logger("application").exception(
            "unhandled_application_error",
            request_id=getattr(request.state, "request_id", "unknown"),
        )
        return _problem(request, 500, "internal_error", "Internal server error", "The request could not be completed.")

    @app.get("/healthz", tags=["Operations"], include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Report process liveness without probing dependencies."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["Operations"], include_in_schema=False)
    async def readyz() -> dict[str, Any]:
        """Report readiness; dependency checks are added with database/queue adapters."""
        return {"status": "ready", "checks": {"api": "ok"}}

    @app.get("/metrics", tags=["Operations"], include_in_schema=False)
    async def metrics(request: Request) -> Response:
        """Expose metrics only when a strong bearer token is configured and presented."""
        token = resolved.metrics_scrape_token
        authorization = request.headers.get("authorization", "")
        supplied = authorization.removeprefix("Bearer ")
        if token is None or not hmac.compare_digest(supplied, token.get_secret_value()):
            return _problem(request, 403, "permission_denied", "Forbidden", "Metrics access is not authorized.")
        return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()

