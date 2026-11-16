"""SQL adapter behavior tests using deterministic async-session fakes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from rag.adapters.postgres.ingestion import PostgresIngestionRepository
from rag.domain.auth import IdempotencyConflict
from rag.domain.ports.ingestion import IngestionChunk, QueueCapacityExceeded


class ExecuteResult:
    def __init__(self, value: object = None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


class ScalarRows:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def __iter__(self):
        return iter(self.values)

    def all(self) -> list[object]:
        return self.values


class FakeSession:
    def __init__(
        self,
        *,
        scalars: list[object] | None = None,
        execute_values: list[object] | None = None,
        scalar_rows: list[object] | None = None,
    ) -> None:
        self.scalar_values = list(scalars or [])
        self.execute_values = list(execute_values or [])
        self.scalar_rows = list(scalar_rows or [])
        self.statements: list[object] = []
        self.added: list[object] = []

    async def scalar(self, statement: object) -> object:
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def execute(self, statement: object, *args: object, **kwargs: object) -> ExecuteResult:
        self.statements.append(statement)
        value = self.execute_values.pop(0) if self.execute_values else None
        return value if isinstance(value, ExecuteResult) else ExecuteResult(value)

    async def scalars(self, statement: object) -> ScalarRows:
        self.statements.append(statement)
        rows = self.scalar_rows.pop(0) if self.scalar_rows else []
        return ScalarRows(list(rows))

    def add(self, value: object) -> None:
        self.added.append(value)


class FakeDatabase:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    @asynccontextmanager
    async def tenant_session(self, tenant_id, principal_id=None):
        yield self.session


def _repo(session: FakeSession) -> PostgresIngestionRepository:
    return PostgresIngestionRepository(FakeDatabase(session))


@pytest.mark.asyncio
async def test_req_fr_ing_001_repository_creates_document_and_job() -> None:
    tenant, collection, document, job = (uuid4() for _ in range(4))
    session = FakeSession(
        scalars=[collection, None, 0],
        execute_values=[None, None, ExecuteResult(uuid4())],
    )

    result = await _repo(session).create_upload(
        tenant,
        collection,
        document,
        job,
        "a" * 64,
        "handbook.pdf",
        200,
        {"source": "manual"},
        f"{tenant}/{document}.pdf",
        "b" * 64,
        "c" * 64,
        10,
    )

    assert (result.document_id, result.job_id, result.created) == (document, job, True)
    assert len(session.added) == 2
    assert len(session.statements) == 6


@pytest.mark.asyncio
async def test_quarantine_decision_updates_chunk_and_creates_tenant_audit() -> None:
    tenant, actor, chunk_id = uuid4(), uuid4(), uuid4()
    chunk = SimpleNamespace(quarantined=True, quarantine_status="pending")
    session = FakeSession(scalars=[None, chunk])

    status, result = await _repo(session).decide_quarantined(
        tenant,
        actor,
        chunk_id,
        "approve",
        "Reviewed and accepted",
        "a" * 64,
        "b" * 64,
    )

    assert status == "recorded"
    assert chunk.quarantined is False and chunk.quarantine_status == "approved"
    assert len(session.added) == 1
    audit = session.added[0]
    assert audit.tenant_id == tenant
    assert audit.actor_key_id == actor
    assert audit.chunk_id == chunk_id and audit.decision == "approve"


@pytest.mark.asyncio
async def test_quarantine_decision_replays_idempotently_and_rejects_key_reuse() -> None:
    tenant, actor, chunk_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    existing = SimpleNamespace(
        request_digest="b" * 64,
        chunk_id=chunk_id,
        decision="reject",
        reason="Unsafe",
        created_at=now,
    )
    session = FakeSession(scalars=[existing])
    status, response = await _repo(session).decide_quarantined(
        tenant, actor, chunk_id, "reject", "Unsafe", "a" * 64, "b" * 64
    )
    assert status == "reject" and response["decided_at"] == now
    assert session.added == []

    session = FakeSession(scalars=[existing])
    with pytest.raises(IdempotencyConflict):
        await _repo(session).decide_quarantined(
            tenant, actor, chunk_id, "approve", "Different", "a" * 64, "c" * 64
        )


@pytest.mark.asyncio
async def test_repository_reuses_idempotency_record_and_rejects_digest_conflict() -> None:
    tenant, collection, document, job = (uuid4() for _ in range(4))
    idem = SimpleNamespace(request_digest="c" * 64, result_resource_id=document)
    session = FakeSession(
        scalars=[collection, idem, SimpleNamespace(id=document), SimpleNamespace(id=job)],
        execute_values=[None, None, ExecuteResult(None)],
    )
    result = await _repo(session).create_upload(
        tenant,
        collection,
        uuid4(),
        uuid4(),
        "a" * 64,
        "same.pdf",
        10,
        {},
        "key",
        "b" * 64,
        "c" * 64,
        4,
    )
    assert (result.document_id, result.job_id, result.created) == (document, job, False)

    conflict = SimpleNamespace(request_digest="d" * 64, result_resource_id=document)
    session = FakeSession(
        scalars=[collection, conflict], execute_values=[None, None, ExecuteResult(None)]
    )
    with pytest.raises(IdempotencyConflict):
        await _repo(session).create_upload(
            tenant,
            collection,
            uuid4(),
            uuid4(),
            "a" * 64,
            "same.pdf",
            10,
            {},
            "key",
            "b" * 64,
            "c" * 64,
            4,
        )

    missing_collection = FakeSession(scalars=[None])
    with pytest.raises(LookupError, match="collection_not_found"):
        await _repo(missing_collection).create_upload(
            tenant,
            collection,
            uuid4(),
            uuid4(),
            "a" * 64,
            "missing.pdf",
            10,
            {},
            "key",
            "b" * 64,
            "c" * 64,
            4,
        )

    missing_idempotency_result = FakeSession(
        scalars=[collection, None], execute_values=[None, None, ExecuteResult(None)]
    )
    with pytest.raises(IdempotencyConflict):
        await _repo(missing_idempotency_result).create_upload(
            tenant,
            collection,
            uuid4(),
            uuid4(),
            "a" * 64,
            "unknown.pdf",
            10,
            {},
            "key",
            "b" * 64,
            "c" * 64,
            4,
        )

    duplicate_without_job = FakeSession(
        scalars=[collection, SimpleNamespace(id=uuid4()), None],
        execute_values=[None, None, ExecuteResult(uuid4())],
    )
    with pytest.raises(LookupError, match="content_dedup_job_missing"):
        await _repo(duplicate_without_job).create_upload(
            tenant,
            collection,
            uuid4(),
            uuid4(),
            "a" * 64,
            "duplicate.pdf",
            10,
            {},
            "key",
            "b" * 64,
            "c" * 64,
            4,
        )


@pytest.mark.asyncio
async def test_repository_deduplicates_content_and_bounds_queue() -> None:
    tenant, collection, document, job = (uuid4() for _ in range(4))
    duplicate = SimpleNamespace(id=document)
    prior_job = SimpleNamespace(id=job)
    session = FakeSession(
        scalars=[collection, duplicate, prior_job],
        execute_values=[None, None, ExecuteResult(uuid4()), None],
    )
    result = await _repo(session).create_upload(
        tenant,
        collection,
        uuid4(),
        uuid4(),
        "a" * 64,
        "same.pdf",
        10,
        {},
        "key",
        "b" * 64,
        "c" * 64,
        4,
    )
    assert (result.document_id, result.job_id, result.created) == (document, job, False)

    session = FakeSession(
        scalars=[collection, None, 4], execute_values=[None, None, ExecuteResult(uuid4())]
    )
    with pytest.raises(QueueCapacityExceeded):
        await _repo(session).create_upload(
            tenant,
            collection,
            uuid4(),
            uuid4(),
            "a" * 64,
            "full.pdf",
            10,
            {},
            "key",
            "b" * 64,
            "c" * 64,
            4,
        )


@pytest.mark.asyncio
async def test_repository_document_and_job_reads_shape_contract_fields() -> None:
    tenant, document_id, job_id = uuid4(), uuid4(), uuid4()
    doc = SimpleNamespace(
        id=document_id,
        collection_id=uuid4(),
        name="file.pdf",
        size_bytes=100,
        status="ready",
        page_count=5,
        metadata_json={"source": "manual"},
        created_at="created",
        updated_at="updated",
        storage_key="private/key",
    )
    job = SimpleNamespace(
        id=job_id,
        status="ready",
        progress=100,
        stage="ready",
        retryable=False,
        error_code=None,
        created_at="created",
        updated_at="updated",
        document_id=document_id,
        kind="ingest",
    )
    session = FakeSession(scalars=[doc, job])
    result = await _repo(session).get_document(tenant, document_id)
    assert result is not None and result["filename"] == "file.pdf"
    assert result["error_code"] is None
    session = FakeSession(scalars=[job])
    result = await _repo(session).get_job(tenant, job_id)
    assert result is not None and result["kind"] == "ingest"
    assert await _repo(FakeSession()).get_document(tenant, document_id) is None
    assert await _repo(FakeSession()).get_job(tenant, job_id) is None

    no_ingestion_job = SimpleNamespace(
        id=document_id,
        collection_id=uuid4(),
        name="file.pdf",
        size_bytes=0,
        status="queued",
        page_count=None,
        metadata_json={},
        created_at="created",
        updated_at="updated",
        storage_key="",
    )
    result = await _repo(FakeSession(scalars=[no_ingestion_job, None])).get_document(
        tenant, document_id
    )
    assert result is not None and result["error_code"] is None


@pytest.mark.asyncio
async def test_repository_list_uses_bounded_cursor_page() -> None:
    tenant, first = uuid4(), uuid4()
    row = SimpleNamespace(
        id=first,
        collection_id=uuid4(),
        name="file.pdf",
        size_bytes=10,
        status="queued",
        page_count=None,
        metadata_json={},
        created_at="now",
        updated_at="now",
        storage_key="hidden",
    )
    session = FakeSession(scalar_rows=[[row, SimpleNamespace()]])
    items, cursor = await _repo(session).list_documents(tenant, None, None, None, 1)
    assert len(items) == 1 and cursor == first
    session = FakeSession(scalar_rows=[[row]])
    items, cursor = await _repo(session).list_documents(tenant, uuid4(), "ready", first, 5)
    assert len(items) == 1 and cursor is None


@pytest.mark.asyncio
async def test_repository_retry_delete_and_cancel_transitions() -> None:
    tenant, job_id, doc_id = uuid4(), uuid4(), uuid4()
    previous = SimpleNamespace(
        id=job_id, status="failed", retryable=True, document_id=doc_id, kind="delete"
    )
    document = SimpleNamespace(id=doc_id, status="failed")
    session = FakeSession(scalars=[previous, document], execute_values=[ExecuteResult(uuid4())])
    new_job = await _repo(session).retry_job(tenant, job_id, "a" * 64, "b" * 64)
    assert new_job is not None and document.status == "deleting"

    queued_delete = SimpleNamespace(id=job_id, status="queued", document_id=doc_id, kind="delete")
    session = FakeSession(scalars=[queued_delete])
    result = await _repo(session).cancel_job(tenant, job_id)
    assert result == {"id": job_id, "document_id": doc_id}
    assert queued_delete.status == "cancelled"

    session = FakeSession(scalars=[SimpleNamespace(id=job_id, status="processing")])
    assert await _repo(session).cancel_job(tenant, job_id) is None

    session = FakeSession(scalars=[SimpleNamespace(id=job_id, status="failed", retryable=False)])
    assert await _repo(session).retry_job(tenant, job_id, "c" * 64, "d" * 64) is None
    previous = SimpleNamespace(
        id=job_id, status="failed", retryable=True, document_id=doc_id, kind="ingest"
    )
    session = FakeSession(scalars=[previous, None])
    assert await _repo(session).retry_job(tenant, job_id, "c" * 64, "d" * 64) is None


@pytest.mark.asyncio
async def test_repository_queue_delete_is_idempotent_and_cancels_ingestion() -> None:
    tenant, doc_id, job_id = uuid4(), uuid4(), uuid4()
    doc = SimpleNamespace(id=doc_id, status="ready")
    session = FakeSession(scalars=[doc, None])
    result = await _repo(session).queue_delete(tenant, doc_id)
    assert result is not None and doc.status == "deleting" and len(session.added) == 1

    active = SimpleNamespace(id=job_id)
    session = FakeSession(scalars=[doc, active])
    assert await _repo(session).queue_delete(tenant, doc_id) == job_id

    doc.status = "deleted"
    session = FakeSession(scalars=[doc, None])
    assert await _repo(session).queue_delete(tenant, doc_id) is None
    assert await _repo(FakeSession()).queue_delete(tenant, doc_id) is None

    ingest = SimpleNamespace(id=uuid4(), status="queued", document_id=doc_id, kind="ingest")
    session = FakeSession(scalars=[ingest])
    assert await _repo(session).cancel_job(tenant, ingest.id) is not None


@pytest.mark.asyncio
async def test_repository_progress_failure_and_delete_completion_are_tenant_scoped() -> None:
    tenant, doc_id, job_id = uuid4(), uuid4(), uuid4()
    repository = _repo(FakeSession())
    await repository.load_for_processing(tenant, doc_id)
    await repository.set_progress(tenant, doc_id, job_id, "processing", 30)
    await repository.fail_processing(tenant, doc_id, job_id, "pdf_invalid")
    await repository.finish_processing(
        tenant,
        doc_id,
        job_id,
        [IngestionChunk(0, "safe text", 1, None, False)],
        [[0.1] * 768],
        1,
    )
    await repository.finish_deletion(tenant, doc_id, job_id)
    await repository.fail_deletion(tenant, job_id)

    processing_doc = SimpleNamespace(id=doc_id, status="processing", collection_id=uuid4())
    session = FakeSession(scalars=[processing_doc], scalar_rows=[[uuid4()]])
    repository = _repo(session)
    await repository.finish_processing(
        tenant,
        doc_id,
        job_id,
        [
            IngestionChunk(0, "safe text", 1, None, False),
            IngestionChunk(1, "quarantined", 2, None, True),
        ],
        [[0.1] * 768, None],
        2,
    )
    assert len(session.added) == 2
    await repository.finish_deletion(tenant, doc_id, job_id)
    assert any("?|" in str(statement) for statement in session.statements)

    deleting_doc = SimpleNamespace(id=doc_id, status="deleting")
    session = FakeSession(scalars=[deleting_doc])
    await _repo(session).finish_processing(tenant, doc_id, job_id, [], [], 0)
    assert session.added == []
