"""Tenant administrator API-key lifecycle endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag.api.dependencies import _key_service, require_scope
from rag.core.errors import ProblemException
from rag.domain.auth import ApiKeyRecord, Principal, Scope
from rag.domain.auth import IdempotencyConflict
from rag.services.api_keys import ApiKeyService, InvalidKeyGrant

router = APIRouter(prefix="/v1/admin/api-keys", tags=["Admin"])
AdminPrincipal = Annotated[Principal, Depends(require_scope(Scope.ADMIN))]


class ApiKeyInput(BaseModel):
    """Validated one-time API-key issuance request."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    scopes: set[Scope] = Field(min_length=1)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("expires_at")
    @classmethod
    def require_aware_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return value


class ApiKeyPublic(BaseModel):
    """Non-secret API-key metadata returned by list and create operations."""

    id: str
    name: str
    scopes: list[Scope]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked: bool


class ApiKeyCreated(BaseModel):
    """One-time secret issuance response."""

    key: ApiKeyPublic
    secret: str


class PageInfo(BaseModel):
    """Cursor pagination metadata."""

    next_cursor: str | None = None
    has_more: bool


class ApiKeyPage(BaseModel):
    """Bounded page of tenant key metadata."""

    items: list[ApiKeyPublic]
    page: PageInfo


def _public_key(record: ApiKeyRecord) -> ApiKeyPublic:
    return ApiKeyPublic(
        id=str(record.id),
        name=record.name,
        scopes=sorted(record.scopes, key=lambda item: item.value),
        created_at=record.created_at,
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        revoked=record.revoked_at is not None,
    )


@router.get("", response_model=ApiKeyPage)
async def list_api_keys(
    request: Request,
    principal: AdminPrincipal,
    cursor: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ApiKeyPage:
    """Return tenant-only key metadata with a bounded UUID keyset cursor."""
    service = _key_service(request)
    try:
        parsed_cursor = UUID(cursor) if cursor is not None else None
    except ValueError as exc:
        raise ProblemException(
            422, "validation_failed", "Validation failed", "cursor must be a valid key UUID."
        ) from exc
    records = await service.list_keys(principal.tenant_id, parsed_cursor, limit + 1)
    has_more = len(records) > limit
    items = records[:limit]
    next_cursor = str(items[-1].id) if has_more and items else None
    return ApiKeyPage(
        items=[_public_key(record) for record in items],
        page=PageInfo(next_cursor=next_cursor, has_more=has_more),
    )


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    payload: ApiKeyInput,
    request: Request,
    principal: AdminPrincipal,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=32, max_length=128, pattern=r"^[!-~]+$"),
    ],
) -> ApiKeyCreated:
    """Issue a hashed tenant key; plaintext is returned once and never persisted."""
    service = _key_service(request)
    try:
        record, secret = await service.issue(
            principal,
            payload.name,
            frozenset(payload.scopes),
            payload.expires_at.astimezone(UTC) if payload.expires_at is not None else None,
            idempotency_key,
        )
    except InvalidKeyGrant as exc:
        raise ProblemException(
            403, "permission_denied", "Forbidden", "Requested scopes exceed caller authority."
        ) from exc
    except IdempotencyConflict as exc:
        raise ProblemException(
            409,
            "idempotency_conflict",
            "Conflict",
            "This idempotency key was already used; no additional key was created and its secret is not replayed.",
        ) from exc
    return ApiKeyCreated(key=_public_key(record), secret=secret)


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: UUID,
    request: Request,
    principal: AdminPrincipal,
) -> Response:
    """Revoke only a key owned by the authenticated tenant; repeated calls are safe."""
    service: ApiKeyService = _key_service(request)
    found = await service.revoke(principal.tenant_id, key_id)
    if not found:
        raise ProblemException(404, "not_found", "Not found", "API key was not found.")
    return Response(status_code=204)
