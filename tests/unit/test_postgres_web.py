"""Repository tests for the workspace PostgreSQL adapter using a tenant session fake."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest

from rag.adapters.postgres.models import Collection, Conversation, Message, QueryLog
from rag.adapters.postgres.web import PostgresWebRepository
from rag.db.session import Database


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class _Result:
    def __init__(self, value: Any = None, row: tuple[int, int, int] = (2, 8, 13)) -> None:
        self.value = value
        self.row = row

    def scalar_one_or_none(self) -> Any:
        return self.value

    def one(self) -> tuple[int, int, int]:
        return self.row


class _Session:
    def __init__(
        self,
        *,
        scalar_rows: list[Any] | None = None,
        many_rows: list[Any] | None = None,
        result: _Result | None = None,
    ) -> None:
        self.scalar_rows = list(scalar_rows or [])
        self.many_rows = many_rows or []
        self.result = result or _Result(uuid4())
        self.added: list[Any] = []
        self.added_many: list[Any] = []
        self.flushes = 0
        self.executions = 0

    async def scalar(self, _: Any) -> Any:
        return self.scalar_rows.pop(0) if self.scalar_rows else None

    async def scalars(self, _: Any) -> _Rows:
        return _Rows(self.many_rows)

    async def execute(self, _: Any) -> _Result:
        self.executions += 1
        return self.result

    def add(self, row: Any) -> None:
        self.added.append(row)

    def add_all(self, rows: list[Any]) -> None:
        self.added_many.extend(rows)

    async def flush(self) -> None:
        self.flushes += 1
        now = datetime.now(UTC)
        for row in self.added:
            if isinstance(row, (Collection, Conversation)):
                row.created_at = now
                row.updated_at = now


class _Database:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.contexts: list[tuple[Any, ...]] = []

    @asynccontextmanager
    async def tenant_session(self, *identity: Any) -> AsyncIterator[_Session]:
        self.contexts.append(identity)
        yield self.session


def _collection(tenant_id: Any, name: str = "Policy") -> Collection:
    now = datetime.now(UTC)
    return Collection(
        id=uuid4(),
        tenant_id=tenant_id,
        name=name,
        description="A tenant collection",
        created_at=now,
        updated_at=now,
    )


def _conversation(tenant_id: Any, key_id: Any, title: str = "New conversation") -> Conversation:
    now = datetime.now(UTC)
    return Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        owner_key_id=key_id,
        title=title,
        pinned=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_collection_repository_pages_creates_updates_and_deletes() -> None:
    tenant_id = uuid4()
    first, second = _collection(tenant_id, "One"), _collection(tenant_id, "Two")
    row_session = _Session(many_rows=[first, second])
    repo = PostgresWebRepository(cast(Database, _Database(row_session)))
    rows, cursor = await repo.list_collections(tenant_id, None, 1, "pol")
    assert len(rows) == 1 and rows[0]["name"] == "One"
    assert cursor == first.id

    created_session = _Session()
    repo = PostgresWebRepository(cast(Database, _Database(created_session)))
    created = await repo.create_collection(tenant_id, "Created", None)
    assert created["name"] == "Created" and created_session.flushes == 1

    existing = _collection(tenant_id)
    session = _Session(scalar_rows=[existing, None, existing], result=_Result(existing.id))
    repo = PostgresWebRepository(cast(Database, _Database(session)))
    assert (await repo.get_collection(tenant_id, existing.id))["id"] == str(existing.id)
    assert await repo.update_collection(tenant_id, uuid4(), {"name": "Missing"}) is None
    updated = await repo.update_collection(tenant_id, existing.id, {"name": "Renamed"})
    assert updated is not None and updated["name"] == "Renamed"
    assert await repo.delete_collection(tenant_id, existing.id)

    missing_delete = _Session(result=_Result(None))
    assert not await PostgresWebRepository(
        cast(Database, _Database(missing_delete))
    ).delete_collection(tenant_id, uuid4())


@pytest.mark.asyncio
async def test_conversation_and_message_repository_is_owner_scoped_and_paged() -> None:
    tenant_id, key_id = uuid4(), uuid4()
    first, second = _conversation(tenant_id, key_id, "One"), _conversation(tenant_id, key_id, "Two")
    page_session = _Session(many_rows=[first, second])
    repo = PostgresWebRepository(cast(Database, _Database(page_session)))
    rows, cursor = await repo.list_conversations(tenant_id, key_id, None, 1, "pol")
    assert len(rows) == 1 and cursor == first.id

    created_session = _Session()
    created = await PostgresWebRepository(
        cast(Database, _Database(created_session))
    ).create_conversation(tenant_id, key_id, "Question")
    assert created["title"] == "Question" and created_session.added[0].owner_key_id == key_id

    message = Message(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=first.id,
        role="assistant",
        content="Grounded response",
        citations=[{"chunk_id": "synthetic-chunk"}],
        request_id="req-test",
        created_at=datetime.now(UTC),
    )
    session = _Session(scalar_rows=[first, first, first.id], many_rows=[message])
    repo = PostgresWebRepository(cast(Database, _Database(session)))
    assert (await repo.get_conversation(tenant_id, key_id, first.id))["id"] == str(first.id)
    assert (await repo.update_conversation(tenant_id, key_id, first.id, {"pinned": True}))[
        "pinned"
    ] is True
    assert await repo.delete_conversation(tenant_id, key_id, first.id)
    messages, next_cursor = await repo.list_messages(tenant_id, key_id, first.id, None, 10)
    assert messages[0]["citations"][0]["chunk_id"] == "synthetic-chunk"
    assert next_cursor is None

    hidden = _Session(scalar_rows=[None])
    assert (
        await PostgresWebRepository(cast(Database, _Database(hidden))).list_messages(
            tenant_id, key_id, uuid4(), None, 10
        )
        is None
    )


@pytest.mark.asyncio
async def test_append_exchange_updates_title_and_feedback_is_idempotent() -> None:
    tenant_id, key_id = uuid4(), uuid4()
    conversation = _conversation(tenant_id, key_id)
    session = _Session(scalar_rows=[conversation])
    repo = PostgresWebRepository(cast(Database, _Database(session)))
    assert await repo.append_exchange(
        tenant_id, key_id, conversation.id, "A policy question", "A supported answer", [], "req-1"
    )
    assert len(session.added_many) == 2
    assert conversation.title == "A policy question"
    assert session.flushes == 1

    missing = _Session(scalar_rows=[None])
    assert not await PostgresWebRepository(cast(Database, _Database(missing))).append_exchange(
        tenant_id, key_id, uuid4(), "q", "a", [], "req-2"
    )

    query_log = QueryLog(
        id=uuid4(),
        tenant_id=tenant_id,
        key_id=key_id,
        question="q",
        retrieved_ids=[],
        request_id="req-feedback",
    )
    states = [None, query_log, query_log, query_log]
    query_log.feedback = "up"
    query_log.feedback_reason = "Helpful"
    session = _Session(scalar_rows=states)
    repo = PostgresWebRepository(cast(Database, _Database(session)))
    assert await repo.feedback(tenant_id, key_id, "missing", "up", None) == "not_found"
    assert await repo.feedback(tenant_id, key_id, "req-feedback", "up", "Helpful") == "same"
    assert await repo.feedback(tenant_id, key_id, "req-feedback", "down", None) == "conflict"
    query_log.feedback = None
    assert await repo.feedback(tenant_id, key_id, "req-feedback", "down", "Reason") == "recorded"


@pytest.mark.asyncio
async def test_usage_aggregation_returns_explicitly_unpriced_cost() -> None:
    tenant_id = uuid4()
    since, until = datetime.now(UTC), datetime.now(UTC)
    session = _Session(result=_Result(row=(3, 21, 34)))
    repo = PostgresWebRepository(cast(Database, _Database(session)))
    usage = await repo.usage(tenant_id, since, until)
    assert usage["query_count"] == 3
    assert usage["input_tokens"] == 21 and usage["output_tokens"] == 34
    assert usage["estimated_cost_usd"] is None
