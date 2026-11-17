"""PostgreSQL adapter for web workspace queries under tenant RLS."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from rag.adapters.postgres.models import Collection, Conversation, Message, QueryLog
from rag.db.session import Database
from rag.domain.ports.web import WebRepository


def _collection(row: Collection) -> dict[str, object]:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _conversation(row: Conversation) -> dict[str, object]:
    return {
        "id": str(row.id),
        "title": row.title,
        "pinned": row.pinned,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _message(row: Message) -> dict[str, object]:
    return {
        "id": str(row.id),
        "role": row.role,
        "content": row.content,
        "citations": row.citations,
        "request_id": row.request_id,
        "created_at": row.created_at.isoformat(),
    }


class PostgresWebRepository(WebRepository):
    """Perform web data access with an explicit tenant transaction per operation."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_collections(
        self, tenant_id: UUID, cursor: UUID | None, limit: int, search: str | None
    ) -> tuple[list[dict[str, object]], UUID | None]:
        statement = select(Collection).where(Collection.tenant_id == tenant_id)
        if cursor is not None:
            statement = statement.where(Collection.id > cursor)
        if search:
            statement = statement.where(Collection.name.ilike(f"%{search}%"))
        statement = statement.order_by(Collection.id.asc()).limit(limit + 1)
        async with self._database.tenant_session(tenant_id) as session:
            rows = list((await session.scalars(statement)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return [_collection(row) for row in rows], rows[-1].id if has_more and rows else None

    async def create_collection(
        self, tenant_id: UUID, name: str, description: str | None
    ) -> dict[str, object]:
        row = Collection(id=uuid4(), tenant_id=tenant_id, name=name, description=description)
        async with self._database.tenant_session(tenant_id) as session:
            session.add(row)
            await session.flush()
            return _collection(row)

    async def get_collection(
        self, tenant_id: UUID, collection_id: UUID
    ) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id) as session:
            row = await session.scalar(
                select(Collection).where(
                    Collection.tenant_id == tenant_id, Collection.id == collection_id
                )
            )
            return _collection(row) if row is not None else None

    async def update_collection(
        self, tenant_id: UUID, collection_id: UUID, values: dict[str, object]
    ) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id) as session:
            row = await session.scalar(
                select(Collection).where(
                    Collection.tenant_id == tenant_id, Collection.id == collection_id
                )
            )
            if row is None:
                return None
            for key, value in values.items():
                setattr(row, key, value)
            await session.flush()
            return _collection(row)

    async def delete_collection(self, tenant_id: UUID, collection_id: UUID) -> bool:
        async with self._database.tenant_session(tenant_id) as session:
            result = await session.execute(
                delete(Collection)
                .where(Collection.tenant_id == tenant_id, Collection.id == collection_id)
                .returning(Collection.id)
            )
            return result.scalar_one_or_none() is not None

    async def create_conversation(
        self, tenant_id: UUID, key_id: UUID, title: str
    ) -> dict[str, object]:
        row = Conversation(
            id=uuid4(), tenant_id=tenant_id, owner_key_id=key_id, title=title, pinned=False
        )
        async with self._database.tenant_session(tenant_id, key_id) as session:
            session.add(row)
            await session.flush()
            return _conversation(row)

    async def list_conversations(
        self,
        tenant_id: UUID,
        key_id: UUID,
        cursor: UUID | None,
        limit: int,
        search: str | None,
    ) -> tuple[list[dict[str, object]], UUID | None]:
        statement = select(Conversation).where(
            Conversation.tenant_id == tenant_id, Conversation.owner_key_id == key_id
        )
        if cursor is not None:
            statement = statement.where(Conversation.id < cursor)
        if search:
            statement = statement.where(Conversation.title.ilike(f"%{search}%"))
        statement = statement.order_by(Conversation.pinned.desc(), Conversation.id.desc()).limit(
            limit + 1
        )
        async with self._database.tenant_session(tenant_id, key_id) as session:
            rows = list((await session.scalars(statement)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return [_conversation(row) for row in rows], rows[-1].id if has_more and rows else None

    async def get_conversation(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID
    ) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id, key_id) as session:
            row = await session.scalar(
                select(Conversation).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.owner_key_id == key_id,
                    Conversation.id == conversation_id,
                )
            )
            return _conversation(row) if row is not None else None

    async def update_conversation(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID, values: dict[str, object]
    ) -> dict[str, object] | None:
        async with self._database.tenant_session(tenant_id, key_id) as session:
            row = await session.scalar(
                select(Conversation).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.owner_key_id == key_id,
                    Conversation.id == conversation_id,
                )
            )
            if row is None:
                return None
            for key, value in values.items():
                setattr(row, key, value)
            await session.flush()
            return _conversation(row)

    async def delete_conversation(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID
    ) -> bool:
        async with self._database.tenant_session(tenant_id, key_id) as session:
            result = await session.execute(
                delete(Conversation)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.owner_key_id == key_id,
                    Conversation.id == conversation_id,
                )
                .returning(Conversation.id)
            )
            return result.scalar_one_or_none() is not None

    async def list_messages(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID, cursor: UUID | None, limit: int
    ) -> tuple[list[dict[str, object]], UUID | None] | None:
        async with self._database.tenant_session(tenant_id, key_id) as session:
            owner = await session.scalar(
                select(Conversation.id).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.owner_key_id == key_id,
                    Conversation.id == conversation_id,
                )
            )
            if owner is None:
                return None
            statement = select(Message).where(
                Message.tenant_id == tenant_id, Message.conversation_id == conversation_id
            )
            if cursor is not None:
                statement = statement.where(Message.id < cursor)
            statement = statement.order_by(Message.id.desc()).limit(limit + 1)
            rows = list((await session.scalars(statement)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return [_message(row) for row in rows], rows[-1].id if has_more and rows else None

    async def append_exchange(
        self,
        tenant_id: UUID,
        key_id: UUID,
        conversation_id: UUID,
        question: str,
        answer: str,
        citations: list[dict[str, object]],
        request_id: str,
    ) -> bool:
        async with self._database.tenant_session(tenant_id, key_id) as session:
            conversation = await session.scalar(
                select(Conversation)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.owner_key_id == key_id,
                    Conversation.id == conversation_id,
                )
                .with_for_update()
            )
            if conversation is None:
                return False
            session.add_all(
                [
                    Message(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        role="user",
                        content=question,
                        request_id=request_id,
                    ),
                    Message(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        role="assistant",
                        content=answer,
                        citations=citations,
                        request_id=request_id,
                    ),
                ]
            )
            if conversation.title == "New conversation":
                conversation.title = question[:120].strip() or "New conversation"
            conversation.updated_at = datetime.now(UTC)
            await session.flush()
            return True

    async def feedback(
        self,
        tenant_id: UUID,
        key_id: UUID,
        request_id: str,
        rating: str,
        reason: str | None,
    ) -> str:
        async with self._database.tenant_session(tenant_id, key_id) as session:
            row = await session.scalar(
                select(QueryLog).where(
                    QueryLog.tenant_id == tenant_id,
                    QueryLog.key_id == key_id,
                    QueryLog.request_id == request_id,
                )
            )
            if row is None:
                return "not_found"
            if row.feedback is not None:
                return (
                    "same"
                    if (row.feedback, row.feedback_reason) == (rating, reason)
                    else "conflict"
                )
            row.feedback = rating
            row.feedback_reason = reason
            await session.flush()
            return "recorded"

    async def usage(self, tenant_id: UUID, since: datetime, until: datetime) -> dict[str, object]:
        async with self._database.tenant_session(tenant_id) as session:
            row = (
                await session.execute(
                    select(
                        func.count(QueryLog.id),
                        func.coalesce(func.sum(QueryLog.input_tokens), 0),
                        func.coalesce(func.sum(QueryLog.output_tokens), 0),
                    ).where(
                        QueryLog.tenant_id == tenant_id,
                        QueryLog.created_at >= since,
                        QueryLog.created_at < until,
                    )
                )
            ).one()
        return {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "query_count": int(row[0] or 0),
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "estimated_cost_usd": None,
            "cost_note": "Provider price schedule is not configured.",
        }
