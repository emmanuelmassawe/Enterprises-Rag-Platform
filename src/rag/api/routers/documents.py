"""Tenant-scoped document upload, listing, and ingestion job endpoints."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePath
from typing import Annotated, cast
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from rag.api.dependencies import require_scope
from rag.core.errors import ProblemException
from rag.domain.auth import IdempotencyConflict, Principal, Scope
from rag.domain.ports.ingestion import (
    BlobStore,
    IngestionApplication,
    IngestionRepository,
    QueueBackend,
    QueueUnavailable,
    StorageUnavailable,
    UploadRejected,
)

router = APIRouter(prefix="/v1", tags=["Documents", "Jobs"])
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{32,128}$")
METADATA_KEYS = {"source", "department", "category", "tags"}
UPLOAD_CHUNK_SIZE = 1024 * 1024


class QuarantineDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(min_length=1, max_length=1000)


def _service(request: Request) -> IngestionApplication:
    service = getattr(request.app.state, "ingestion_service", None)
    if service is None:
        raise ProblemException(
            503, "dependency_unavailable", "Unavailable", "Ingestion is not configured."
        )
    return cast(IngestionApplication, service)


def _repository(request: Request) -> IngestionRepository:
    repository = getattr(request.app.state, "ingestion_repository", None)
    if repository is None:
        raise ProblemException(
            503, "dependency_unavailable", "Unavailable", "Ingestion storage is unavailable."
        )
    return cast(IngestionRepository, repository)


def _queue(request: Request) -> QueueBackend:
    queue = getattr(request.app.state, "ingestion_queue", None)
    if queue is None:
        raise ProblemException(
            503, "dependency_unavailable", "Unavailable", "Ingestion queue is unavailable."
        )
    return cast(QueueBackend, queue)


def _metadata(value: str | None) -> dict[str, str | int | float | bool | None]:
    if not value:
        return {}
    if len(value) > 4096:
        raise ProblemException(
            422, "validation_failed", "Validation failed", "Metadata is too large."
        )
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProblemException(
            422, "validation_failed", "Validation failed", "Metadata must be valid JSON."
        ) from exc
    if not isinstance(parsed, dict) or parsed.keys() - METADATA_KEYS or len(parsed) > 16:
        raise ProblemException(
            422, "validation_failed", "Validation failed", "Metadata contains unsupported fields."
        )
    if any(not isinstance(item, (str, int, float, bool, type(None))) for item in parsed.values()):
        raise ProblemException(
            422, "validation_failed", "Validation failed", "Metadata values must be scalar."
        )
    return parsed


def _validate_upload_headers(
    request: Request, file: UploadFile, idempotency_key: str, collection_id: str
) -> tuple[UUID, str]:
    settings = request.app.state.settings
    if not IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise ProblemException(
            422,
            "validation_failed",
            "Validation failed",
            "Idempotency-Key must be 32-128 safe characters.",
        )
    declared_length = request.headers.get("content-length")
    if (
        declared_length
        and declared_length.isdigit()
        and int(declared_length) > settings.blob_max_upload_bytes + 65_536
    ):
        raise ProblemException(
            413,
            "upload_too_large",
            "Upload too large",
            "The uploaded file exceeds the configured limit.",
        )
    if file.content_type != "application/pdf" or not (file.filename or "").lower().endswith(".pdf"):
        raise ProblemException(
            415,
            "unsupported_media_type",
            "Unsupported media type",
            "Only PDF uploads are accepted.",
        )
    try:
        collection_uuid = UUID(collection_id)
    except ValueError as exc:
        raise ProblemException(
            422, "validation_failed", "Validation failed", "collection_id must be a UUID."
        ) from exc
    safe_name = PurePath((file.filename or "").replace("\\", "/")).name
    if not safe_name or len(safe_name) > 255 or any(ord(character) < 32 for character in safe_name):
        raise ProblemException(
            422, "validation_failed", "Validation failed", "The filename is invalid."
        )
    return collection_uuid, safe_name


async def _inspect_upload(file: UploadFile, max_bytes: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    prefix = b""
    while block := await file.read(UPLOAD_CHUNK_SIZE):
        size += len(block)
        if size > max_bytes:
            await file.close()
            raise ProblemException(
                413,
                "upload_too_large",
                "Upload too large",
                "The uploaded file exceeds the configured limit.",
            )
        digest.update(block)
        if len(prefix) < 5:
            prefix += block[: 5 - len(prefix)]
    if prefix != b"%PDF-":
        raise ProblemException(
            415,
            "unsupported_media_type",
            "Unsupported media type",
            "The file does not contain a PDF header.",
        )
    await file.seek(0)
    return size, digest.hexdigest()


def _ingestion_problem(exc: Exception) -> ProblemException:
    if isinstance(exc, UploadRejected):
        return ProblemException(
            413, "upload_too_large", "Upload too large", "The upload violates configured limits."
        )
    if isinstance(exc, QueueUnavailable):
        return ProblemException(
            503,
            "queue_unavailable",
            "Service unavailable",
            "The ingestion queue cannot accept work.",
            {"Retry-After": "5"},
        )
    if isinstance(exc, StorageUnavailable):
        return ProblemException(
            503,
            "storage_unavailable",
            "Service unavailable",
            "Document storage is temporarily unavailable.",
            {"Retry-After": "5"},
        )
    if isinstance(exc, IdempotencyConflict):
        return ProblemException(
            409,
            "idempotency_conflict",
            "Conflict",
            "The idempotency key was already used for different content.",
        )
    if isinstance(exc, LookupError):
        return ProblemException(
            422,
            "collection_not_found",
            "Validation failed",
            "The collection does not exist in this tenant.",
        )
    raise exc


async def _accept_upload(
    request: Request,
    principal: Principal,
    file: UploadFile,
    collection_id: UUID,
    filename: str,
    size: int,
    content_hash: str,
    idempotency_key: str,
    metadata: dict[str, str | int | float | bool | None],
) -> tuple[UUID, UUID, bool]:
    blob_store = cast(BlobStore, request.app.state.blob_store)
    storage_key = f"{principal.tenant_id}/{uuid4()}.pdf"
    try:
        return await _service(request).accept_upload(
            tenant_id=principal.tenant_id,
            collection_id=collection_id,
            filename=filename,
            content_type=file.content_type,
            size_bytes=size,
            content_hash=content_hash,
            idempotency_key=idempotency_key,
            metadata=metadata,
            storage_key=storage_key,
            source=file.file,
        )
    except (
        UploadRejected,
        QueueUnavailable,
        StorageUnavailable,
        IdempotencyConflict,
        LookupError,
    ) as exc:
        raise _ingestion_problem(exc) from exc
    except SQLAlchemyError as exc:
        structlog.get_logger("ingestion").warning(
            "upload_persistence_failed", request_id=request.state.request_id
        )
        await blob_store.delete(storage_key)
        raise ProblemException(
            503,
            "storage_unavailable",
            "Service unavailable",
            "Document storage is temporarily unavailable.",
            {"Retry-After": "5"},
        ) from exc


@router.post("/documents", status_code=202, operation_id="uploadDocument")
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    collection_id: Annotated[str, Form(min_length=1, max_length=80)],
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    metadata: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    """Accept one size-bounded PDF and enqueue a private asynchronous ingestion job."""
    settings = request.app.state.settings
    collection_uuid, safe_name = _validate_upload_headers(
        request, file, idempotency_key, collection_id
    )
    size, content_hash = await _inspect_upload(file, settings.blob_max_upload_bytes)
    document_id, job_id, _created = await _accept_upload(
        request,
        principal,
        file,
        collection_uuid,
        safe_name,
        size,
        content_hash,
        idempotency_key,
        _metadata(metadata),
    )
    document = await _repository(request).get_document(principal.tenant_id, document_id)
    job = await _repository(request).get_job(principal.tenant_id, job_id)
    if document is None or job is None:
        raise ProblemException(
            503,
            "ingestion_unavailable",
            "Service unavailable",
            "The accepted upload could not be read back.",
        )
    document.pop("storage_key", None)
    job.pop("document_id", None)
    job.pop("kind", None)
    return {"document": document, "job": job, "request_id": request.state.request_id}


@router.get("/documents", operation_id="listDocuments")
async def list_documents(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
    collection_id: UUID | None = None,
    status: str | None = Query(
        default=None, pattern="^(queued|processing|ready|failed|deleting|deleted)$"
    ),
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    items, next_cursor = await _repository(request).list_documents(
        principal.tenant_id, collection_id, status, cursor, limit
    )
    for item in items:
        item.pop("storage_key", None)
    return {
        "items": items,
        "page": {
            "next_cursor": str(next_cursor) if next_cursor else None,
            "has_more": next_cursor is not None,
        },
    }


@router.get("/documents/{document_id}", operation_id="getDocument")
async def get_document(
    request: Request,
    document_id: UUID,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
) -> dict[str, object]:
    document = await _repository(request).get_document(principal.tenant_id, document_id)
    if document is None:
        raise ProblemException(404, "not_found", "Not found", "Document was not found.")
    document.pop("storage_key", None)
    return document


@router.delete("/documents/{document_id}", status_code=202, operation_id="deleteDocument")
async def delete_document(
    request: Request,
    document_id: UUID,
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
) -> dict[str, object]:
    job_id = await _repository(request).queue_delete(principal.tenant_id, document_id)
    if job_id is None:
        document = await _repository(request).get_document(principal.tenant_id, document_id)
        if document is None:
            raise ProblemException(404, "not_found", "Not found", "Document was not found.")
        return {
            "operation_id": str(document_id),
            "status": "completed",
            "request_id": request.state.request_id,
        }
    job = await _repository(request).get_job(principal.tenant_id, job_id)
    if job is None:
        raise ProblemException(
            503,
            "ingestion_unavailable",
            "Service unavailable",
            "The deletion job could not be read back.",
        )
    try:
        await _queue(request).enqueue_delete(principal.tenant_id, document_id, job_id)
    except Exception as exc:
        raise ProblemException(
            503,
            "queue_unavailable",
            "Service unavailable",
            "The deletion queue cannot accept work.",
            {"Retry-After": "5"},
        ) from exc
    return {
        "operation_id": str(job_id),
        "job_id": str(job_id),
        "status": "accepted" if job["status"] == "queued" else "processing",
        "request_id": request.state.request_id,
    }


@router.get("/jobs/{job_id}", operation_id="getJob")
async def get_job(
    request: Request,
    job_id: UUID,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
) -> dict[str, object]:
    job = await _repository(request).get_job(principal.tenant_id, job_id)
    if job is None:
        raise ProblemException(404, "not_found", "Not found", "Job was not found.")
    job.pop("document_id", None)
    job.pop("kind", None)
    return job


@router.delete("/jobs/{job_id}", status_code=202, operation_id="cancelJob")
async def cancel_job(
    request: Request,
    job_id: UUID,
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
) -> dict[str, object]:
    cancelled = await _repository(request).cancel_job(principal.tenant_id, job_id)
    if cancelled is None:
        job = await _repository(request).get_job(principal.tenant_id, job_id)
        if job is None:
            raise ProblemException(404, "not_found", "Not found", "Job was not found.")
        raise ProblemException(
            409, "job_not_cancellable", "Conflict", "Only queued jobs can be cancelled."
        )
    job = await _repository(request).get_job(principal.tenant_id, job_id)
    if job is None:
        raise ProblemException(404, "not_found", "Not found", "Job was not found.")
    job.pop("document_id", None)
    job.pop("kind", None)
    return job


@router.post("/jobs/{job_id}/retry", status_code=202, operation_id="retryJob")
async def retry_job(
    request: Request,
    job_id: UUID,
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    if not IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise ProblemException(
            422,
            "validation_failed",
            "Validation failed",
            "Idempotency-Key must be 32-128 safe characters.",
        )
    request_digest = hashlib.sha256(f"retry:{job_id}".encode()).hexdigest()
    idempotency_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    try:
        new_job_id = await _repository(request).retry_job(
            principal.tenant_id, job_id, idempotency_hash, request_digest
        )
    except IdempotencyConflict as exc:
        raise ProblemException(
            409,
            "idempotency_conflict",
            "Conflict",
            "The idempotency key was already used for a different retry.",
        ) from exc
    if new_job_id is None:
        raise ProblemException(
            409, "job_not_retryable", "Conflict", "The job is not eligible for retry."
        )
    job = await _repository(request).get_job(principal.tenant_id, new_job_id)
    if job is None:
        raise ProblemException(
            503,
            "ingestion_unavailable",
            "Service unavailable",
            "The retry job could not be read back.",
        )
    document_id = cast(UUID, job["document_id"])
    try:
        if job.get("kind") == "delete":
            await _queue(request).enqueue_delete(principal.tenant_id, document_id, new_job_id)
        else:
            await _queue(request).enqueue(principal.tenant_id, document_id, new_job_id)
    except Exception as exc:
        raise ProblemException(
            503,
            "queue_unavailable",
            "Service unavailable",
            "The ingestion queue cannot accept work.",
            {"Retry-After": "5"},
        ) from exc
    job.pop("document_id", None)
    job.pop("kind", None)
    return job


@router.get("/admin/quarantine", operation_id="listQuarantine")
async def list_quarantine(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.ADMIN))],
    document_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    items, next_cursor = await _repository(request).list_quarantined(
        principal.tenant_id, document_id, cursor, limit
    )
    return {
        "items": items,
        "page": {
            "next_cursor": str(next_cursor) if next_cursor else None,
            "has_more": next_cursor is not None,
        },
    }


@router.get("/admin/quarantine/{chunk_id}", operation_id="getQuarantineItem")
async def get_quarantine_item(
    request: Request,
    chunk_id: UUID,
    principal: Annotated[Principal, Depends(require_scope(Scope.ADMIN))],
) -> dict[str, object]:
    item = await _repository(request).get_quarantined(principal.tenant_id, chunk_id)
    if item is None:
        raise ProblemException(404, "not_found", "Not found", "Quarantine item was not found.")
    return item


@router.post("/admin/quarantine/{chunk_id}/decision", operation_id="decideQuarantine")
async def decide_quarantine(
    request: Request,
    chunk_id: UUID,
    body: QuarantineDecisionInput,
    principal: Annotated[Principal, Depends(require_scope(Scope.ADMIN))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    if not IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise ProblemException(
            422,
            "validation_failed",
            "Validation failed",
            "Idempotency-Key must be 32-128 safe characters.",
        )
    idempotency_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request_digest = hashlib.sha256(
        f"quarantine:{chunk_id}:{body.decision}:{body.reason}".encode()
    ).hexdigest()
    try:
        status, result = await _repository(request).decide_quarantined(
            principal.tenant_id,
            principal.key_id,
            chunk_id,
            body.decision,
            body.reason,
            idempotency_hash,
            request_digest,
        )
    except IdempotencyConflict as exc:
        raise ProblemException(
            409,
            "idempotency_conflict",
            "Conflict",
            "The idempotency key was already used for a different decision.",
        ) from exc
    if status == "not_found":
        raise ProblemException(404, "not_found", "Not found", "Quarantine item was not found.")
    decision_record = cast(dict[str, object], result)
    return {
        "chunk_id": str(chunk_id),
        "decision": decision_record["decision"],
        "decided_at": decision_record["decided_at"],
        "request_id": request.state.request_id,
    }
