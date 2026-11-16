"""Ports and immutable records for tenant-scoped retrieval and generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class QueryUnavailable(RuntimeError):
    """A required retrieval, embedding, audit, or generation dependency failed."""


class QueryValidationError(ValueError):
    """The request cannot be safely or unambiguously processed."""


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: UUID
    document_id: UUID
    filename: str
    page: int | None
    section: str | None
    content: str
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class GeneratedClaim:
    text: str
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GenerationResult:
    claims: tuple[GeneratedClaim, ...]
    refusal_code: str | None
    input_tokens: int
    output_tokens: int
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CitationRecord:
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    section: str | None
    quote: str


@dataclass(frozen=True, slots=True)
class QueryResultRecord:
    answer: str
    citations: tuple[CitationRecord, ...]
    refusal: dict[str, str] | None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None
    request_id: str
    retrieval_debug: dict[str, object] | None = None


class QueryRepository(Protocol):
    """Tenant-bound PostgreSQL search and query-audit operations."""

    async def dense_search(
        self,
        tenant_id: UUID,
        collection_ids: list[UUID],
        vector: list[float],
        filters: dict[str, str | int | float | bool],
        limit: int,
        minimum_similarity: float,
    ) -> list[RetrievedChunk]: ...

    async def full_text_search(
        self,
        tenant_id: UUID,
        collection_ids: list[UUID],
        question: str,
        filters: dict[str, str | int | float | bool],
        limit: int,
    ) -> list[RetrievedChunk]: ...

    async def get_eligible_chunks(
        self, tenant_id: UUID, collection_ids: list[UUID], chunk_ids: list[UUID]
    ) -> list[RetrievedChunk]: ...

    async def record_query(
        self,
        tenant_id: UUID,
        key_id: UUID,
        request_id: str,
        question: str,
        chunk_ids: list[str],
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None: ...


class QueryEmbeddingProvider(Protocol):
    """Create query vectors in the same embedding space used during ingestion."""

    async def embed(self, contents: list[str]) -> list[list[float]]: ...


class AnswerGenerator(Protocol):
    """Generate strict, citation-bearing claims from bounded evidence."""

    async def generate(self, system_instruction: str, user_content: str) -> GenerationResult: ...

    async def close(self) -> None: ...


class QueryCache(Protocol):
    """Fail-open cache for versioned tenant query responses."""

    async def get(self, tenant_id: UUID, cache_key: str) -> dict[str, object] | None: ...

    async def set(
        self, tenant_id: UUID, cache_key: str, value: dict[str, object], ttl_seconds: int
    ) -> None: ...

    async def invalidate_tenant(self, tenant_id: UUID) -> None: ...


class QueryApplication(Protocol):
    """Application use case consumed by the HTTP adapter."""

    async def answer(
        self,
        *,
        tenant_id: UUID,
        key_id: UUID,
        request_id: str,
        question: str,
        collection_ids: list[UUID],
        top_k: int,
        filters: dict[str, str | int | float | bool],
        debug: bool = False,
        conversation_id: UUID | None = None,
    ) -> QueryResultRecord: ...
