"""Query endpoint with JSON and versioned Server-Sent Events responses."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag.api.dependencies import require_scope
from rag.core.errors import ProblemException
from rag.domain.auth import Principal, Role, Scope
from rag.domain.ports.query import (
    QueryApplication,
    QueryResultRecord,
    QueryUnavailable,
    QueryValidationError,
)

router = APIRouter(prefix="/v1", tags=["Query"])


class QueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=8000)
    collection_ids: list[UUID] = Field(min_length=1, max_length=3)
    conversation_id: UUID | None = None
    stream: bool = False
    top_k: int = Field(default=8, ge=1, le=20)
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=10)
    debug: bool = False

    @field_validator("collection_ids")
    @classmethod
    def unique_collections(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("collection_ids must be unique")
        return value


class CitationOutput(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    section: str | None
    quote: str


class QueryOutput(BaseModel):
    answer: str
    citations: list[CitationOutput]
    refusal: dict[str, str] | None
    usage: dict[str, int | float | None]
    request_id: str
    retrieval_debug: dict[str, object] | None = None


def _service(request: Request) -> QueryApplication:
    service = getattr(request.app.state, "query_service", None)
    if service is None:
        raise ProblemException(
            503, "dependency_unavailable", "Unavailable", "Query service is not configured."
        )
    return cast(QueryApplication, service)


def _output(result: QueryResultRecord, include_debug: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "answer": result.answer,
        "citations": [asdict(citation) for citation in result.citations],
        "refusal": result.refusal,
        "usage": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "estimated_cost_usd": result.estimated_cost_usd,
        },
        "request_id": result.request_id,
    }
    if include_debug and result.retrieval_debug is not None:
        payload["retrieval_debug"] = result.retrieval_debug
    return payload


def _event(name: str, request_id: str, **payload: object) -> bytes:
    data = {"contract_version": "rag.query.v1", "request_id": request_id, **payload}
    encoded = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    return f"event: {name}\ndata: {encoded}\n\n".encode()


async def _run_query(
    request: Request, body: QueryInput, principal: Principal, service: QueryApplication
) -> QueryResultRecord:
    try:
        return await service.answer(
            tenant_id=principal.tenant_id,
            key_id=principal.key_id,
            request_id=request.state.request_id,
            question=body.question,
            collection_ids=body.collection_ids,
            top_k=body.top_k,
            filters=body.filters,
            debug=body.debug and principal.role == Role.ADMIN,
            conversation_id=body.conversation_id,
        )
    except QueryValidationError as exc:
        raise ProblemException(
            422, str(exc), "Invalid query", "The query request is invalid."
        ) from exc
    except QueryUnavailable as exc:
        raise ProblemException(
            503,
            "query_unavailable",
            "Query unavailable",
            "The query could not be completed.",
            {"Retry-After": "5"},
        ) from exc


@router.post("/query", response_model=None)
async def query(
    body: QueryInput,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
    service: Annotated[QueryApplication, Depends(_service)],
) -> object:
    """Answer from tenant-authorized collection evidence."""
    if not body.stream:
        result = await _run_query(request, body, principal, service)
        return _output(result, body.debug and principal.role == Role.ADMIN)

    async def events() -> AsyncIterator[bytes]:
        request_id = request.state.request_id
        yield _event(
            "retrieval_started",
            request_id,
            collection_ids=[str(item) for item in body.collection_ids],
        )
        try:
            result = await _run_query(request, body, principal, service)
            output = _output(result, body.debug and principal.role == Role.ADMIN)
            yield _event("citations", request_id, citations=output["citations"])
            if result.refusal is not None:
                yield _event("refusal", request_id, **result.refusal)
            else:
                # The validated response is emitted in provisional pieces per the contract.
                for sequence, offset in enumerate(range(0, len(result.answer), 128), start=1):
                    if await request.is_disconnected():
                        return
                    yield _event(
                        "token",
                        request_id,
                        text=result.answer[offset : offset + 128],
                        sequence=sequence,
                    )
                    await asyncio.sleep(0)
            yield _event("done", request_id, usage=output["usage"])
        except ProblemException as exc:
            yield _event(
                "error",
                request_id,
                problem={
                    "status": exc.status,
                    "code": exc.code,
                    "title": exc.title,
                    "detail": exc.detail,
                },
            )
        except Exception:
            yield _event(
                "error",
                request_id,
                problem={
                    "status": 503,
                    "code": "query_unavailable",
                    "title": "Query unavailable",
                    "detail": "The query could not be completed.",
                },
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
