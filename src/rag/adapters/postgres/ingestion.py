"""Tenant-scoped persistence for uploads, ingestion jobs, and indexed chunks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Text, cast, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, insert

from rag.adapters.postgres.models import (
    Chunk,
    Collection,
    Document,
    IdempotencyRecord,
    Job,
    QuarantineDecision,
    QueryLog,
)
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

    def __init__(
        self, database: Database, embedding_model: str = "gemini-embedding-2", dimensions: int = 768
    ) -> None:
        self._database = database
        self._embedding_model = embedding_model
        self._embedding_dimensions = dimensions

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
            if (
                await session.scalar(
                    select(Collection.id).where(
                        Collection.tenant_id == tenant_id, Collection.id == collection_id
                    )
                )
                is None
            ):
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
            duplicate = await session.scalar(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.collection_id == collection_id,
                    Document.content_hash == content_hash,
                )
            )
            if duplicate is not None:
                prior_job = await session.scalar(
                    select(Job)
                    .where(
                        Job.tenant_id == tenant_id,
                        Job.document_id == duplicate.id,
                        Job.kind == "ingest",
                    )
                    .order_by(Job.created_at.desc())
                    .limit(1)
                )
                if prior_job is None:
                    raise LookupError("content_dedup_job_missing")
                await session.execute(
                    update(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.tenant_id == tenant_id,
                        IdempotencyRecord.key_hash == idempotency_hash,
                    )
                    .values(result_resource_id=duplicate.id)
                )
                return UploadResult(duplicate.id, prior_job.id, False)
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
                "kind": row.kind,
            }

    async def retry_job(
        self, tenant_id: UUID, job_id: UUID, idempotency_hash: str, request_digest: str
    ) -> UUID | None:
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
            now = datetime.now(UTC)
            claim = await session.execute(
                insert(IdempotencyRecord)
                .values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    key_hash=idempotency_hash,
                    request_digest=request_digest,
                    result_resource_id=new_job_id,
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
                    raise IdempotencyConflict("idempotency key conflicts with a prior retry")
                return existing.result_resource_id
            document.status = "deleting" if previous.kind == "delete" else "queued"
            session.add(
                Job(
                    id=new_job_id,
                    tenant_id=tenant_id,
                    document_id=document.id,
                    kind=previous.kind,
                    status="queued",
                    stage="queued",
                )
            )
            return new_job_id

    async def queue_delete(self, tenant_id: UUID, document_id: UUID) -> UUID | None:
        async with self._database.tenant_session(tenant_id) as session:
            document = await session.scalar(
                select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
            )
            if document is None:
                return None
            existing = await session.scalar(
                select(Job)
                .where(
                    Job.tenant_id == tenant_id,
                    Job.document_id == document_id,
                    Job.kind == "delete",
                    Job.status.in_(["queued", "processing"]),
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            if existing is not None:
                return existing.id
            if document.status == "deleted":
                return None
            job_id = uuid4()
            await session.execute(
                update(Job)
                .where(
                    Job.tenant_id == tenant_id,
                    Job.document_id == document_id,
                    Job.kind == "ingest",
                    Job.status.in_(["queued", "processing"]),
                )
                .values(status="cancelled", stage="cancelled")
            )
            document.status = "deleting"
            session.add(
                Job(
                    id=job_id,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    kind="delete",
                    status="queued",
                    stage="queued",
                )
            )
            return job_id

    async def cancel_job(self, tenant_id: UUID, job_id: UUID) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id) as session:
            job = await session.scalar(
                select(Job).where(Job.tenant_id == tenant_id, Job.id == job_id)
            )
            if job is None or job.status != "queued":
                return None
            job.status = "cancelled"
            job.stage = "cancelled"
            if job.document_id is not None:
                await session.execute(
                    update(Document)
                    .where(Document.tenant_id == tenant_id, Document.id == job.document_id)
                    .values(status="ready" if job.kind == "delete" else "failed")
                )
            return {"id": job.id, "document_id": job.document_id}

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
                .where(
                    Document.tenant_id == tenant_id,
                    Document.id == document_id,
                    Document.status.notin_(["deleting", "deleted"]),
                )
                .values(status=status)
            )
            await session.execute(
                update(Job)
                .where(
                    Job.tenant_id == tenant_id,
                    Job.id == job_id,
                    Job.status.in_(["queued", "processing"]),
                )
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
                select(Document)
                .where(Document.tenant_id == tenant_id, Document.id == document_id)
                .with_for_update()
            )
            if document is None or document.status != "processing":
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
                        quarantine_status="pending" if chunk.quarantined else "clear",
                        trust_level=chunk.trust_level,
                        metadata_json={"reason_codes": list(chunk.reason_codes)},
                        embedding_model=self._embedding_model if embedding is not None else None,
                        embedding_dimensions=self._embedding_dimensions
                        if embedding is not None
                        else None,
                    )
                )
            document.status = "ready"
            document.page_count = page_count
            await session.execute(
                update(Job)
                .where(Job.tenant_id == tenant_id, Job.id == job_id)
                .values(
                    status="ready", stage="ready", progress=100, error_code=None, retryable=False
                )
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
                    retryable=error_code
                    in {"embedding_provider_unavailable", "storage_unavailable"},
                )
            )

    async def finish_deletion(self, tenant_id: UUID, document_id: UUID, job_id: UUID) -> None:
        async with self._database.tenant_session(tenant_id) as session:
            chunk_ids = [
                str(chunk_id)
                for chunk_id in await session.scalars(
                    select(Chunk.id).where(
                        Chunk.tenant_id == tenant_id, Chunk.document_id == document_id
                    )
                )
            ]
            if chunk_ids:
                await session.execute(
                    delete(QueryLog).where(
                        QueryLog.tenant_id == tenant_id,
                        QueryLog.retrieved_ids.op("?|")(cast(chunk_ids, ARRAY(Text))),
                    )
                )
            await session.execute(
                delete(Chunk).where(Chunk.tenant_id == tenant_id, Chunk.document_id == document_id)
            )
            await session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.tenant_id == tenant_id,
                    IdempotencyRecord.result_resource_id == document_id,
                )
            )
            await session.execute(
                update(Document)
                .where(Document.tenant_id == tenant_id, Document.id == document_id)
                .values(
                    name="deleted.pdf",
                    content_hash="0" * 64,
                    storage_key="",
                    size_bytes=0,
                    page_count=None,
                    metadata_json={},
                    status="deleted",
                )
            )
            await session.execute(
                update(Job)
                .where(Job.tenant_id == tenant_id, Job.id == job_id)
                .values(status="ready", stage="completed", progress=100, retryable=False)
            )

    async def fail_deletion(self, tenant_id: UUID, job_id: UUID) -> None:
        async with self._database.tenant_session(tenant_id) as session:
            await session.execute(
                update(Job)
                .where(Job.tenant_id == tenant_id, Job.id == job_id)
                .values(
                    status="failed",
                    stage="failed",
                    error_code="blob_delete_failed",
                    retryable=True,
                )
            )

    async def list_quarantined(
        self, tenant_id: UUID, document_id: UUID | None, cursor: UUID | None, limit: int
    ) -> tuple[list[dict[str, object]], UUID | None]:
        async with self._database.tenant_session(tenant_id) as session:
            statement = (
                select(Chunk)
                .where(Chunk.tenant_id == tenant_id, Chunk.quarantine_status == "pending")
                .order_by(Chunk.id)
                .limit(limit + 1)
            )
            if document_id is not None:
                statement = statement.where(Chunk.document_id == document_id)
            if cursor is not None:
                statement = statement.where(Chunk.id > cursor)
            rows = list((await session.execute(statement)).all())
            has_more = len(rows) > limit
            rows = rows[:limit]
            items = [_quarantine_item(chunk, include_text=True) for (chunk,) in rows]
            return items, (rows[-1][0].id if has_more and rows else None)

    async def get_quarantined(self, tenant_id: UUID, chunk_id: UUID) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id) as session:
            row = await session.execute(
                select(Chunk).where(
                    Chunk.tenant_id == tenant_id,
                    Chunk.id == chunk_id,
                    Chunk.quarantine_status == "pending",
                )
            )
            result = row.one_or_none()
            return _quarantine_item(result[0], include_text=True) if result else None

    async def decide_quarantined(
        self,
        tenant_id: UUID,
        actor_key_id: UUID,
        chunk_id: UUID,
        decision: str,
        reason: str,
        idempotency_hash: str,
        request_digest: str,
    ) -> tuple[str, object]:
        from rag.domain.auth import IdempotencyConflict

        async with self._database.tenant_session(tenant_id) as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"quarantine:{tenant_id}:{idempotency_hash}"},
            )
            existing = await session.scalar(
                select(QuarantineDecision).where(
                    QuarantineDecision.tenant_id == tenant_id,
                    QuarantineDecision.idempotency_hash == idempotency_hash,
                )
            )
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise IdempotencyConflict("idempotency key conflicts with prior decision")
                return existing.decision, {
                    "chunk_id": str(existing.chunk_id),
                    "decision": existing.decision,
                    "reason": existing.reason,
                    "decided_at": existing.created_at,
                }
            chunk = await session.scalar(
                select(Chunk)
                .where(
                    Chunk.tenant_id == tenant_id,
                    Chunk.id == chunk_id,
                    Chunk.quarantine_status == "pending",
                )
                .with_for_update()
            )
            if chunk is None:
                return "not_found", {}
            chunk.quarantined = decision != "approve"
            chunk.quarantine_status = "approved" if decision == "approve" else "rejected"
            now = datetime.now(UTC)
            session.add(
                QuarantineDecision(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    chunk_id=chunk_id,
                    actor_key_id=actor_key_id,
                    decision=decision,
                    reason=reason,
                    idempotency_hash=idempotency_hash,
                    request_digest=request_digest,
                    created_at=now,
                )
            )
            return "recorded", {
                "chunk_id": str(chunk_id),
                "decision": decision,
                "reason": reason,
                "decided_at": now,
            }


def _quarantine_item(chunk: Chunk, *, include_text: bool) -> dict[str, object]:
    item: dict[str, object] = {
        "chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "page": chunk.page,
        "reason_codes": chunk.metadata_json.get("reason_codes", []),
        "created_at": chunk.created_at,
    }
    if include_text:
        item["plain_text"] = chunk.content[:12_000]
    return item
