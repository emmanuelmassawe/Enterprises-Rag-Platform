"""Ports and transport-independent records for document ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page: int
    text: str


class QueueCapacityExceeded(RuntimeError):
    """Tenant's bounded pending-ingestion capacity is exhausted."""


class UploadRejected(ValueError):
    """Upload violates its media, size, or metadata contract."""


class QueueUnavailable(RuntimeError):
    """The durable ingestion queue cannot currently accept a job."""


class StorageUnavailable(RuntimeError):
    """Private object storage is temporarily unavailable."""


@dataclass(frozen=True, slots=True)
class IngestionChunk:
    ordinal: int
    content: str
    page: int | None
    section: str | None
    quarantined: bool
    trust_level: str = "untrusted"
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UploadResult:
    document_id: UUID
    job_id: UUID
    created: bool


class BlobStore(Protocol):
    """Private storage for tenant document objects."""

    async def put(self, key: str, source: BinaryIO) -> None: ...

    async def download(self, key: str, destination: BinaryIO) -> None: ...

    async def delete(self, key: str) -> None: ...


class IngestionRepository(Protocol):
    """Tenant-scoped persistence operations required by ingestion use cases."""

    async def create_upload(
        self,
        tenant_id: UUID,
        collection_id: UUID,
        document_id: UUID,
        job_id: UUID,
        content_hash: str,
        filename: str,
        size_bytes: int,
        metadata: dict[str, str | int | float | bool | None],
        storage_key: str,
        idempotency_hash: str,
        request_digest: str,
        max_queue_size: int,
    ) -> UploadResult: ...

    async def delete_upload(
        self, tenant_id: UUID, document_id: UUID, idempotency_hash: str
    ) -> None: ...

    async def list_documents(
        self,
        tenant_id: UUID,
        collection_id: UUID | None,
        status: str | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[dict[str, object]], UUID | None]: ...

    async def get_document(
        self, tenant_id: UUID, document_id: UUID
    ) -> dict[str, object] | None: ...

    async def get_job(self, tenant_id: UUID, job_id: UUID) -> dict[str, object] | None: ...

    async def queue_delete(self, tenant_id: UUID, document_id: UUID) -> UUID | None: ...

    async def cancel_job(self, tenant_id: UUID, job_id: UUID) -> dict[str, object] | None: ...

    async def retry_job(
        self, tenant_id: UUID, job_id: UUID, idempotency_hash: str, request_digest: str
    ) -> UUID | None: ...

    async def load_for_processing(
        self, tenant_id: UUID, document_id: UUID
    ) -> dict[str, object] | None: ...

    async def set_progress(
        self, tenant_id: UUID, document_id: UUID, job_id: UUID, status: str, progress: int
    ) -> None: ...

    async def finish_processing(
        self,
        tenant_id: UUID,
        document_id: UUID,
        job_id: UUID,
        chunks: list[IngestionChunk],
        embeddings: list[list[float] | None],
        page_count: int,
    ) -> None: ...

    async def fail_processing(
        self, tenant_id: UUID, document_id: UUID, job_id: UUID, error_code: str
    ) -> None: ...

    async def finish_deletion(self, tenant_id: UUID, document_id: UUID, job_id: UUID) -> None: ...

    async def fail_deletion(self, tenant_id: UUID, job_id: UUID) -> None: ...

    async def list_quarantined(
        self, tenant_id: UUID, document_id: UUID | None, cursor: UUID | None, limit: int
    ) -> tuple[list[dict[str, object]], UUID | None]: ...

    async def get_quarantined(self, tenant_id: UUID, chunk_id: UUID) -> dict[str, object] | None: ...

    async def decide_quarantined(
        self,
        tenant_id: UUID,
        actor_key_id: UUID,
        chunk_id: UUID,
        decision: str,
        reason: str,
        idempotency_hash: str,
        request_digest: str,
    ) -> tuple[str, object]: ...


class QueueBackend(Protocol):
    """Bounded asynchronous ingestion queue."""

    async def enqueue(self, tenant_id: UUID, document_id: UUID, job_id: UUID) -> None: ...

    async def enqueue_delete(self, tenant_id: UUID, document_id: UUID, job_id: UUID) -> None: ...

    async def ping(self) -> bool: ...


class InjectionDetector(Protocol):
    """Identify instruction-like content before indexing or retrieval."""

    def is_suspicious(self, content: str) -> bool: ...

    def reason_codes(self, content: str) -> tuple[str, ...]: ...


class IngestionApplication(Protocol):
    """Ingestion use case exposed to the HTTP adapter."""

    async def accept_upload(
        self,
        *,
        tenant_id: UUID,
        collection_id: UUID,
        filename: str,
        content_type: str | None,
        size_bytes: int,
        content_hash: str,
        idempotency_key: str,
        metadata: dict[str, str | int | float | bool | None],
        storage_key: str,
        source: BinaryIO,
    ) -> tuple[UUID, UUID, bool]: ...
