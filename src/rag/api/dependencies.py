"""FastAPI dependencies for database-backed API key identity and admission control."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from rag.core.errors import ProblemException
from rag.domain.auth import Principal, Scope
from rag.services.api_keys import ApiKeyService, InvalidCredential


def _key_service(request: Request) -> ApiKeyService:
    service = getattr(request.app.state, "api_key_service", None)
    if not isinstance(service, ApiKeyService):
        raise ProblemException(
            503,
            "dependency_unavailable",
            "Service unavailable",
            "Credential storage is unavailable.",
        )
    return service


async def current_principal(request: Request) -> Principal:
    """Authenticate the bearer token, then apply tenant/key-scoped rate limiting."""
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise ProblemException(
            401,
            "authentication_required",
            "Authentication required",
            "A valid bearer API key is required.",
            {"WWW-Authenticate": "Bearer"},
        )
    service = _key_service(request)
    try:
        principal = await service.authenticate(token)
    except InvalidCredential as exc:
        raise ProblemException(
            401,
            "authentication_required",
            "Authentication required",
            "A valid bearer API key is required.",
            {"WWW-Authenticate": "Bearer"},
        ) from exc
    decision = await request.app.state.rate_limiter.consume(
        str(principal.tenant_id),
        str(principal.key_id),
        request.app.state.settings.rate_limit_requests,
        request.app.state.settings.rate_limit_window_seconds,
    )
    request.state.rate_limit = decision
    if not decision.allowed:
        retry_after = max(1, decision.reset_at - int(request.app.state.clock()))
        raise ProblemException(
            429,
            "rate_limited",
            "Rate limit exceeded",
            "Too many requests. Retry after the current limit window.",
            {"Retry-After": str(retry_after)},
        )
    return principal


def require_scope(scope: Scope) -> Callable[..., Awaitable[Principal]]:
    """Create a dependency that requires a specific API key scope."""

    async def check_scope(
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> Principal:
        if not principal.allows(scope):
            raise ProblemException(
                403,
                "permission_denied",
                "Forbidden",
                "The API key does not have the required scope.",
            )
        return principal

    return check_scope
