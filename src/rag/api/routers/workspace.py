"""Tenant-scoped collections, conversation history, feedback and admin summaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError

from rag.api.dependencies import require_scope
from rag.core.errors import ProblemException
from rag.domain.auth import Principal, Scope
from rag.domain.ports.web import WebRepository

router = APIRouter(prefix="/v1", tags=["Workspace"])


class CollectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class CollectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class ConversationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="New conversation", min_length=1, max_length=240)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()


class ConversationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=240)
    pinned: bool | None = None

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    rating: str = Field(pattern="^(up|down)$")
    reason: str | None = Field(default=None, max_length=1000)


def _repo(request: Request) -> WebRepository:
    repository = getattr(request.app.state, "web_repository", None)
    if repository is None:
        raise ProblemException(
            503, "dependency_unavailable", "Unavailable", "Workspace storage is unavailable."
        )
    return cast(WebRepository, repository)


def _page(items: list[dict[str, object]], next_cursor: UUID | None) -> dict[str, object]:
    return {
        "items": items,
        "page": {
            "next_cursor": str(next_cursor) if next_cursor else None,
            "has_more": next_cursor is not None,
        },
    }


@router.get("/collections")
async def list_collections(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, max_length=120),
) -> dict[str, object]:
    items, cursor_out = await _repo(request).list_collections(
        principal.tenant_id, cursor, limit, search
    )
    return _page(items, cursor_out)


@router.post("/collections", status_code=201)
async def create_collection(
    body: CollectionInput,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
) -> dict[str, object]:
    try:
        return await _repo(request).create_collection(
            principal.tenant_id, body.name, body.description
        )
    except IntegrityError as exc:
        raise ProblemException(
            409, "conflict", "Conflict", "A collection with that name exists."
        ) from exc


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
) -> dict[str, object]:
    result = await _repo(request).get_collection(principal.tenant_id, collection_id)
    if result is None:
        raise ProblemException(404, "not_found", "Not found", "Collection was not found.")
    return result


@router.patch("/collections/{collection_id}")
async def update_collection(
    collection_id: UUID,
    body: CollectionPatch,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
) -> dict[str, object]:
    try:
        result = await _repo(request).update_collection(
            principal.tenant_id, collection_id, body.model_dump(exclude_unset=True)
        )
    except IntegrityError as exc:
        raise ProblemException(
            409, "conflict", "Conflict", "A collection with that name exists."
        ) from exc
    if result is None:
        raise ProblemException(404, "not_found", "Not found", "Collection was not found.")
    return result


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
) -> Response:
    if not await _repo(request).delete_collection(principal.tenant_id, collection_id):
        raise ProblemException(404, "not_found", "Not found", "Collection was not found.")
    return Response(status_code=204)


@router.post("/conversations", status_code=201)
async def create_conversation(
    body: ConversationInput,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
) -> dict[str, object]:
    return await _repo(request).create_conversation(
        principal.tenant_id, principal.key_id, body.title
    )


@router.get("/conversations")
async def list_conversations(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, max_length=120),
) -> dict[str, object]:
    items, cursor_out = await _repo(request).list_conversations(
        principal.tenant_id, principal.key_id, cursor, limit, search
    )
    return _page(items, cursor_out)


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    body: ConversationPatch,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
) -> dict[str, object]:
    result = await _repo(request).update_conversation(
        principal.tenant_id,
        principal.key_id,
        conversation_id,
        body.model_dump(exclude_unset=True),
    )
    if result is None:
        raise ProblemException(404, "not_found", "Not found", "Conversation was not found.")
    return result


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
) -> dict[str, object]:
    result = await _repo(request).get_conversation(
        principal.tenant_id, principal.key_id, conversation_id
    )
    if result is None:
        raise ProblemException(404, "not_found", "Not found", "Conversation was not found.")
    return result


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
) -> Response:
    if not await _repo(request).delete_conversation(
        principal.tenant_id, principal.key_id, conversation_id
    ):
        raise ProblemException(404, "not_found", "Not found", "Conversation was not found.")
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    page = await _repo(request).list_messages(
        principal.tenant_id, principal.key_id, conversation_id, cursor, limit
    )
    if page is None:
        raise ProblemException(404, "not_found", "Not found", "Conversation was not found.")
    return _page(*page)


@router.post("/feedback", status_code=202)
async def submit_feedback(
    body: FeedbackInput,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=32, max_length=128)],
) -> dict[str, object]:
    if not idempotency_key.isascii() or not idempotency_key.isprintable():
        raise ProblemException(
            422,
            "validation_failed",
            "Validation failed",
            "Idempotency-Key must be printable ASCII.",
        )
    status = await _repo(request).feedback(
        principal.tenant_id, principal.key_id, body.request_id, body.rating, body.reason
    )
    if status == "not_found":
        raise ProblemException(404, "not_found", "Not found", "Answer was not found.")
    if status == "conflict":
        raise ProblemException(409, "conflict", "Conflict", "Feedback was already recorded.")
    return {"request_id": body.request_id, "status": status}


@router.get("/admin/usage")
async def get_usage(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.ADMIN))],
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    end = until or now
    start = since or end - timedelta(days=30)
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start >= end
        or end > now + timedelta(minutes=1)
    ):
        raise ProblemException(
            422, "validation_failed", "Validation failed", "Use a valid UTC date range."
        )
    if end - start > timedelta(days=366):
        raise ProblemException(
            422, "validation_failed", "Validation failed", "The range cannot exceed one year."
        )
    return await _repo(request).usage(principal.tenant_id, start, end)


@router.get("/admin/status")
async def admin_status(
    request: Request, _: Annotated[Principal, Depends(require_scope(Scope.ADMIN))]
) -> dict[str, object]:
    checks: dict[str, str] = {"api": "ok"}
    for name, probe in (
        ("database", request.app.state.database_probe),
        ("rate_limiter", request.app.state.rate_limiter_probe),
        ("ingestion_queue", request.app.state.ingestion_queue),
    ):
        if probe is None:
            checks[name] = "not_configured"
            continue
        try:
            checks[name] = "ok" if await probe.ping() else "unavailable"
        except Exception:
            checks[name] = "unavailable"
    return {
        "status": "ready" if all(value == "ok" for value in checks.values()) else "degraded",
        "checks": checks,
    }
