from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from rag.adapters.postgres.models import Chunk, QueryLog
from rag.adapters.postgres.query import PostgresQueryRepository


class _Result:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.statements: list[object] = []
        self.added: list[object] = []

    async def execute(self, statement: object) -> _Result:
        self.statements.append(statement)
        return _Result(self.rows)

    def add(self, item: object) -> None:
        self.added.append(item)


class _Database:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.context: list[tuple[object, object]] = []

    @asynccontextmanager
    async def tenant_session(self, tenant_id: object, principal_id: object = None):
        self.context.append((tenant_id, principal_id))
        yield self.session


def _chunk() -> Chunk:
    row = Chunk(
        id=uuid4(),
        tenant_id=uuid4(),
        document_id=uuid4(),
        collection_id=uuid4(),
        ordinal=0,
        content="Annual leave is available.",
        page=3,
        section="Leave",
        quarantined=False,
        quarantine_status="clear",
        trust_level="untrusted",
        embedding_dimensions=2,
    )
    return row


@pytest.mark.asyncio
async def test_dense_and_fts_queries_are_tenant_and_collection_scoped() -> None:
    tenant_id, collection_id = uuid4(), uuid4()
    chunk = _chunk()
    chunk.tenant_id, chunk.collection_id = tenant_id, collection_id
    session = _Session([(chunk, "guide.pdf", 0.2), (chunk, "guide.pdf", 0.9)])
    database = _Database(session)
    repository = PostgresQueryRepository(database, 2)  # type: ignore[arg-type]

    dense = await repository.dense_search(tenant_id, [collection_id], [0.1, 0.2], {}, 5, 0.35)
    lexical = await repository.full_text_search(tenant_id, [collection_id], "leave policy", {}, 5)

    assert len(dense) == 1 and dense[0].score == pytest.approx(0.8)
    assert len(lexical) == 2
    assert all(item.document_id == chunk.document_id for item in lexical)
    assert database.context == [(tenant_id, None), (tenant_id, None)]
    assert all(
        "tenant_id" in str(statement) and "collection_id" in str(statement)
        for statement in session.statements
    )


@pytest.mark.asyncio
async def test_cache_revalidation_query_and_audit_bind_to_tenant_and_key() -> None:
    tenant_id, key_id, collection_id = uuid4(), uuid4(), uuid4()
    chunk = _chunk()
    session = _Session([(chunk, "guide.pdf")])
    database = _Database(session)
    repository = PostgresQueryRepository(database, 2)  # type: ignore[arg-type]

    rows = await repository.get_eligible_chunks(tenant_id, [collection_id], [chunk.id])
    await repository.record_query(tenant_id, key_id, "req-1", "question", [str(chunk.id)], 12, 3, 4)

    assert rows[0].filename == "guide.pdf"
    assert isinstance(session.added[0], QueryLog)
    assert session.added[0].request_id == "req-1"
    assert database.context[-1] == (tenant_id, key_id)


@pytest.mark.asyncio
async def test_empty_cache_revalidation_does_not_issue_unbounded_query() -> None:
    database = _Database(_Session([]))
    repository = PostgresQueryRepository(database, 2)  # type: ignore[arg-type]
    assert await repository.get_eligible_chunks(uuid4(), [uuid4()], []) == []
    assert not database.context
