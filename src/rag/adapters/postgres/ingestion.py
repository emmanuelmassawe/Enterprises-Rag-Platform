"""Tenant-scoped persistence for uploads, ingestion jobs, and indexed chunks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from rag.adapters.postgres.models import Chunk, Collection, Document, IdempotencyRecord, Job
from rag.db.session import Database
from rag.domain.auth import IdempotencyConflict
from rag.domain.ports.ingestion import IngestionChunk, QueueCapacityExceeded, UploadResult


def _document(row: Document) -> dict[str, object]:
    return {
        "id": row.id,
        "collection_id": row.collection_id,
        "filename": row.name,
        "media_type": "application/pdf",
        "size_bytes": row.size_bytes,
        "status": row.status,
        "page_count": row.page_count,
        "metadata": row.metadata_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "error_code": row.error_code if hasattr(row, "error_code") else None,
        "storage_key": row.storage_key,
    }


class PostgresIngestionRepository:
    """RLS-bound SQL operations with idempotent job/document creation."""

    def __init__(self, database: Database) -> None:
        self._database = database

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
    ) -> UploadResult:
        async with self._database.tenant_session(tenant_id) as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:tenant_id))"),
                {"tenant_id": str(tenant_id)},
            )
            active_jobs = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.tenant_id == tenant_id, Job.status.in_(["queued", "processing"]))
                )
                or 0
            )
            if active_jobs >= max_queue_size:
                raise QueueCapacityExceeded("tenant ingestion queue is full")
            if await session.scalar(
                select(Collection.id).where(
                    Collection.tenant_id == tenant_id, Collection.id == collection_id
                )
            ) is None:
                raise LookupError("collection_not_found")
            now = datetime.now(UTC)
            await session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.expires_at <= now)
            )
            claim = await session.execute(
                insert(IdempotencyRecord)
                .values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    key_hash=idempotency_hash,
                    request_digest=request_digest,
                    result_resource_id=document_id,
                    created_at=now,
                    expires_at=now + timedelta(hours=24),
                )
                .on_conflict_do_nothing(constraint="uq_idempotency_tenant_key_hash")
                .returning(IdempotencyRecord.id)
            )
            if claim.scalar_one_or_none() is None:
                existing = await session.scalar(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.tenant_id == tenant_id,
                        IdempotencyRecord.key_hash == idempotency_hash,
                    )
                )
                if existing is None or existing.request_digest != request_digest:
                    raise IdempotencyConflict("idempotency key conflicts with a prior upload")
                document = await session.scalar(
                    select(Document).where(
                        Document.tenant_id == tenant_id,
                        Document.id == existing.result_resource_id,
                    )
                )
                job = await session.scalar(
                    select(Job).where(
                        Job.tenant_id == tenant_id,
                        Job.document_id == existing.result_resource_id,
                        Job.kind == "ingest",
                    )
                )
                if document is None or job is None:
                    raise LookupError("idempotency_result_expired")
                return UploadResult(document.id, job.id, False)
            session.add(
                Document(
                    id=document_id,
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    content_hash=content_hash,
                    name=filename,
                    storage_key=storage_key,
                    size_bytes=size_bytes,
                    metadata_json=metadata,
                )
            )
            session.add(
                Job(
                    id=job_id,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    kind="ingest",
                    status="queued",
                    stage="queued",
                )
            )
            return UploadResult(document_id, job_id, True)

    async def delete_upload(
        self, tenant_id: UUID, document_id: UUID, idempotency_hash: str
    ) -> None:
        async with self._database.tenant_session(tenant_id) as session:
            await session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.tenant_id == tenant_id,
                    IdempotencyRecord.key_hash == idempotency_hash,
                )
            )
            await session.execute(delete(Document).where(Document.id == document_id))

    async def list_documents(
        self,
        tenant_id: UUID,
        collection_id: UUID | None,
        status: str | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[dict[str, object]], UUID | None]:
        statement = select(Document).where(Document.tenant_id == tenant_id)
        if collection_id is not None:
            statement = statement.where(Document.collection_id == collection_id)
        if status is not None:
            statement = statement.where(Document.status == status)
        if cursor is not None:
            statement = statement.where(Document.id < cursor)
        statement = statement.order_by(Document.id.desc()).limit(limit + 1)
        async with self._database.tenant_session(tenant_id) as session:
            rows = list((await session.scalars(statement)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return [_document(row) for row in rows], rows[-1].id if has_more and rows else None

    async def get_document(self, tenant_id: UUID, document_id: UUID) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id) as session:
            row = await session.scalar(
                select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
            )
            if row is None:
                return None
            result = _document(row)
            job = await session.scalar(
                select(Job)
                .where(Job.tenant_id == tenant_id, Job.document_id == document_id)
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            result["error_code"] = job.error_code if job is not None else None
            return result

    async def get_job(self, tenant_id: UUID, job_id: UUID) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id) as session:
            row = await session.scalar(
                select(Job).where(Job.tenant_id == tenant_id, Job.id == job_id)
            )
            if row is None:
                return None
            return {
                "id": row.id,
                "status": row.status,
                "progress": row.progress,
                "stage": row.stage,
                "retryable": row.retryable,
                "error_code": row.error_code,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "document_id": row.document_id,
            }

    async def retry_job(self, tenant_id: UUID, job_id: UUID) -> UUID | None:
        new_job_id = uuid4()
        async with self._database.tenant_session(tenant_id) as session:
            previous = await session.scalar(
                select(Job).where(Job.tenant_id == tenant_id, Job.id == job_id)
            )
            if previous is None or previous.status != "failed" or not previous.retryable:
                return None
            document = await session.scalar(
                select(Document).where(
                    Document.tenant_id == tenant_id, Document.id == previous.document_id
                )
            )
            if document is None:
                return None
            document.status = "queued"
            session.add(
                Job(
                    id=new_job_id,
                    tenant_id=tenant_id,
                    document_id=document.id,
                    kind="ingest",
                    status="queued",
                    stage="queued",
                )
            )
            return new_job_id

    async def load_for_processing(
        self, tenant_id: UUID, document_id: UUID
    ) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id) as session:
            row = await session.scalar(
                select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
            )
            return _document(row) if row is not None else None

    async def set_progress(
        self, tenant_id: UUID, document_id: UUID, job_id: UUID, status: str, progress: int
    ) -> None:
        async with self._database.tenant_session(tenant_id) as session:
            await session.execute(
                update(Document)
                .where(Document.tenant_id == tenant_id, Document.id == document_id)
                .values(status=status)
            )
            await session.execute(
                update(Job)
                .where(Job.tenant_id == tenant_id, Job.id == job_id)
                .values(status=status, stage=status, progress=progress)
            )

    async def finish_processing(
        self,
        tenant_id: UUID,
        document_id: UUID,
        job_id: UUID,
        chunks: list[IngestionChunk],
        embeddings: list[list[float] | None],
        page_count: int,
    ) -> None:
        async with self._database.tenant_session(tenant_id) as session:
            document = await session.scalar(
                select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
            )
            if document is None:
                return
            await session.execute(
                delete(Chunk).where(Chunk.tenant_id == tenant_id, Chunk.document_id == document_id)
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                session.add(
                    Chunk(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        document_id=document_id,
                        collection_id=document.collection_id,
                        ordinal=chunk.ordinal,
                        content=chunk.content,
                        embedding=embedding,
                        page=chunk.page,
                        section=chunk.section,
                        quarantined=chunk.quarantined,
                        embedding_model="configured",
                        embedding_dimensions=len(embedding),
                    )
                )
            document.status = "ready"
            document.page_count = page_count
            await session.execute(
                update(Job)
                .where(Job.tenant_id == tenant_id, Job.id == job_id)
                .values(status="ready", stage="ready", progress=100, error_code=None, retryable=False)
            )

    async def fail_processing(
        self, tenant_id: UUID, document_id: UUID, job_id: UUID, error_code: str
    ) -> None:
        async with self._database.tenant_session(tenant_id) as session:
            await session.execute(
                update(Document)
                .where(Document.tenant_id == tenant_id, Document.id == document_id)
                .values(status="failed")
            )
            await session.execute(
                update(Job)
                .where(Job.tenant_id == tenant_id, Job.id == job_id)
                .values(
                    status="failed",
                    stage="failed",
                    error_code=error_code,
                    retryable=error_code in {"embedding_provider_unavailable", "storage_unavailable"},
                )
            )
