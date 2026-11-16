"""Tenant-bound PostgreSQL hybrid retrieval and query audit adapter."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from uuid import uuid4

from rag.adapters.postgres.models import Chunk, Document, QueryLog
from rag.db.session import Database
from rag.domain.ports.query import RetrievedChunk


class PostgresQueryRepository:
    """Search only ready, eligible chunks inside a tenant-bound RLS transaction."""

    def __init__(self, database: Database, embedding_dimensions: int) -> None:
        self._database = database
        self._embedding_dimensions = embedding_dimensions

    @staticmethod
    def _base(tenant_id: UUID, collection_ids: list[UUID], filters: dict[str, object]):
        statement = (
            select(Chunk, Document.name)
            .join(Document, (Document.id == Chunk.document_id) & (Document.tenant_id == Chunk.tenant_id))
            .where(
                Chunk.tenant_id == tenant_id,
                Chunk.collection_id.in_(collection_ids),
                Document.status == "ready",
                Chunk.quarantined.is_(False),
                Chunk.quarantine_status.in_(["clear", "approved"]),
            )
        )
        for key, value in filters.items():
            statement = statement.where(Chunk.metadata_json[key].astext == str(value))
        return statement

    @staticmethod
    def _to_chunk(chunk: Chunk, filename: str, score: float) -> RetrievedChunk:
        return RetrievedChunk(chunk.id, chunk.document_id, filename, chunk.page, chunk.section, chunk.content, score)

    async def dense_search(
        self, tenant_id: UUID, collection_ids: list[UUID], vector: list[float],
        filters: dict[str, str | int | float | bool], limit: int, minimum_similarity: float,
    ) -> list[RetrievedChunk]:
        async with self._database.tenant_session(tenant_id) as session:
            distance = Chunk.embedding.cosine_distance(vector).label("distance")
            statement = self._base(tenant_id, collection_ids, filters).where(
                Chunk.embedding.is_not(None),
                Chunk.embedding_dimensions == self._embedding_dimensions,
            ).add_columns(distance).order_by(distance).limit(limit)
            rows = (await session.execute(statement)).all()
            return [
                self._to_chunk(chunk, filename, max(0.0, 1.0 - float(distance_value)))
                for chunk, filename, distance_value in rows
                if 1.0 - float(distance_value) >= minimum_similarity
            ]

    async def full_text_search(
        self, tenant_id: UUID, collection_ids: list[UUID], question: str,
        filters: dict[str, str | int | float | bool], limit: int,
    ) -> list[RetrievedChunk]:
        async with self._database.tenant_session(tenant_id) as session:
            query = func.plainto_tsquery("english", question)
            rank = func.ts_rank_cd(Chunk.search_vector, query).label("rank")
            statement = self._base(tenant_id, collection_ids, filters).where(
                Chunk.search_vector.op("@@")(query)
            ).add_columns(rank).order_by(rank.desc()).limit(limit)
            rows = (await session.execute(statement)).all()
            return [self._to_chunk(chunk, filename, float(rank_value)) for chunk, filename, rank_value in rows]

    async def get_eligible_chunks(
        self, tenant_id: UUID, collection_ids: list[UUID], chunk_ids: list[UUID]
    ) -> list[RetrievedChunk]:
        if not chunk_ids:
            return []
        async with self._database.tenant_session(tenant_id) as session:
            statement = self._base(tenant_id, collection_ids, {}).where(Chunk.id.in_(chunk_ids))
            rows = (await session.execute(statement)).all()
            return [self._to_chunk(chunk, filename, 0.0) for chunk, filename in rows]

    async def record_query(
        self, tenant_id: UUID, key_id: UUID, request_id: str, question: str,
        chunk_ids: list[str], latency_ms: int, input_tokens: int, output_tokens: int,
    ) -> None:
        async with self._database.tenant_session(tenant_id, key_id) as session:
            session.add(QueryLog(
                id=uuid4(), tenant_id=tenant_id, key_id=key_id, request_id=request_id,
                question=question, retrieved_ids=chunk_ids, latency_ms=latency_ms,
                input_tokens=input_tokens, output_tokens=output_tokens,
            ))
