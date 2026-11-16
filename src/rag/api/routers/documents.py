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
from sqlalchemy.exc import SQLAlchemyError

from rag.core.errors import ProblemException
from rag.domain.auth import IdempotencyConflict, Principal, Scope
from rag.domain.ports.ingestion import BlobStore, IngestionRepository, QueueBackend
from rag.services.ingestion import IngestionService, QueueUnavailable, UploadRejected
from rag.api.dependencies import require_scope

router = APIRouter(prefix="/v1", tags=["Documents", "Jobs"])
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{32,128}$")
METADATA_KEYS = {"source", "department", "category", "tags"}
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _service(request: Request) -> IngestionService:
    service = getattr(request.app.state, "ingestion_service", None)
    if service is None:
        raise ProblemException(503, "dependency_unavailable", "Unavailable", "Ingestion is not configured.")
    return cast(IngestionService, service)


def _repository(request: Request) -> IngestionRepository:
    repository = getattr(request.app.state, "ingestion_repository", None)
    if repository is None:
        raise ProblemException(503, "dependency_unavailable", "Unavailable", "Ingestion storage is unavailable.")
    return cast(IngestionRepository, repository)


def _queue(request: Request) -> QueueBackend:
    queue = getattr(request.app.state, "ingestion_queue", None)
    if queue is None:
        raise ProblemException(503, "dependency_unavailable", "Unavailable", "Ingestion queue is unavailable.")
    return cast(QueueBackend, queue)


def _metadata(value: str | None) -> dict[str, str | int | float | bool | None]:
    if not value:
        return {}
    if len(value) > 4096:
        raise ProblemException(422, "validation_failed", "Validation failed", "Metadata is too large.")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProblemException(422, "validation_failed", "Validation failed", "Metadata must be valid JSON.") from exc
    if not isinstance(parsed, dict) or parsed.keys() - METADATA_KEYS or len(parsed) > 16:
        raise ProblemException(422, "validation_failed", "Validation failed", "Metadata contains unsupported fields.")
    if any(not isinstance(item, (str, int, float, bool, type(None))) for item in parsed.values()):
        raise ProblemException(422, "validation_failed", "Validation failed", "Metadata values must be scalar.")
    return parsed


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
    if not IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise ProblemException(422, "validation_failed", "Validation failed", "Idempotency-Key must be 32-128 safe characters.")
    settings = request.app.state.settings
    declared_length = request.headers.get("content-length")
    if declared_length and declared_length.isdigit() and int(declared_length) > settings.blob_max_upload_bytes + 65_536:
        raise ProblemException(413, "upload_too_large", "Upload too large", "The uploaded file exceeds the configured limit.")
    if file.content_type != "application/pdf" or not (file.filename or "").lower().endswith(".pdf"):
        raise ProblemException(415, "unsupported_media_type", "Unsupported media type", "Only PDF uploads are accepted.")
    try:
        collection_uuid = UUID(collection_id)
    except ValueError as exc:
        raise ProblemException(422, "validation_failed", "Validation failed", "collection_id must be a UUID.") from exc
    safe_name = PurePath((file.filename or "").replace("\\", "/")).name
    if not safe_name or len(safe_name) > 255 or any(ord(character) < 32 for character in safe_name):
        raise ProblemException(422, "validation_failed", "Validation failed", "The filename is invalid.")
    digest = hashlib.sha256()
    size = 0
    prefix = b""
    while block := await file.read(UPLOAD_CHUNK_SIZE):
        size += len(block)
        if size > settings.blob_max_upload_bytes:
            await file.close()
            raise ProblemException(413, "upload_too_large", "Upload too large", "The uploaded file exceeds the configured limit.")
        digest.update(block)
        if len(prefix) < 5:
            prefix += block[: 5 - len(prefix)]
    if prefix != b"%PDF-":
        raise ProblemException(415, "unsupported_media_type", "Unsupported media type", "The file does not contain a PDF header.")
    await file.seek(0)
    blob_store = cast(BlobStore, request.app.state.blob_store)
    storage_key = f"{principal.tenant_id}/{uuid4()}.pdf"
    try:
        document_id, job_id, created = await _service(request).accept_upload(
            tenant_id=principal.tenant_id,
            collection_id=collection_uuid,
            filename=safe_name,
            content_type=file.content_type,
            size_bytes=size,
            content_hash=digest.hexdigest(),
            idempotency_key=idempotency_key,
            metadata=_metadata(metadata),
            storage_key=storage_key,
            source=file.file,
        )
    except UploadRejected as exc:
        raise ProblemException(413, "upload_too_large", "Upload too large", "The upload violates configured limits.") from exc
    except QueueUnavailable as exc:
        raise ProblemException(503, "queue_unavailable", "Service unavailable", "The ingestion queue cannot accept work.", {"Retry-After": "5"}) from exc
    except IdempotencyConflict as exc:
        raise ProblemException(409, "idempotency_conflict", "Conflict", "The idempotency key was already used for different content.") from exc
    except LookupError as exc:
        raise ProblemException(422, "collection_not_found", "Validation failed", "The collection does not exist in this tenant.") from exc
    except SQLAlchemyError as exc:
        structlog.get_logger("ingestion").warning("upload_persistence_failed", request_id=request.state.request_id)
        await blob_store.delete(storage_key)
        raise ProblemException(503, "storage_unavailable", "Service unavailable", "Document storage is temporarily unavailable.", {"Retry-After": "5"}) from exc
    document = await _repository(request).get_document(principal.tenant_id, document_id)
    job = await _repository(request).get_job(principal.tenant_id, job_id)
    if document is None or job is None:
        raise ProblemException(503, "ingestion_unavailable", "Service unavailable", "The accepted upload could not be read back.")
    document.pop("storage_key", None)
    if not created:
        document["status"] = "queued" if job["status"] == "queued" else document["status"]
    return {"document": document, "job": job, "request_id": request.state.request_id}


@router.get("/documents", operation_id="listDocuments")
async def list_documents(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope(Scope.READ))],
    collection_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(queued|processing|ready|failed|deleting|deleted)$"),
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    items, next_cursor = await _repository(request).list_documents(
        principal.tenant_id, collection_id, status, cursor, limit
    )
    for item in items:
        item.pop("storage_key", None)
    return {"items": items, "page": {"next_cursor": str(next_cursor) if next_cursor else None, "has_more": next_cursor is not None}}


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
    return job


@router.post("/jobs/{job_id}/retry", status_code=202, operation_id="retryJob")
async def retry_job(
    request: Request,
    job_id: UUID,
    principal: Annotated[Principal, Depends(require_scope(Scope.WRITE))],
) -> dict[str, object]:
    new_job_id = await _repository(request).retry_job(principal.tenant_id, job_id)
    if new_job_id is None:
        raise ProblemException(409, "job_not_retryable", "Conflict", "The job is not eligible for retry.")
    job = await _repository(request).get_job(principal.tenant_id, new_job_id)
    if job is None:
        raise ProblemException(503, "ingestion_unavailable", "Service unavailable", "The retry job could not be read back.")
    document_id = cast(UUID, job["document_id"])
    try:
        await _queue(request).enqueue(principal.tenant_id, document_id, new_job_id)
    except Exception as exc:
        raise ProblemException(503, "queue_unavailable", "Service unavailable", "The ingestion queue cannot accept work.", {"Retry-After": "5"}) from exc
    job.pop("document_id", None)
    return job
