"""SQLAlchemy mappings for the tenant-scoped PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    """Base metadata shared by migrations and Postgres adapters."""


class TenantRow:
    """Common tenant discriminator and composite key for tenant-scoped foreign keys."""

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(TenantRow, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    identity_subject: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiKey(TenantRow, Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_api_keys_tenant_id_id"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRecord(TenantRow, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_idempotency_tenant_id_id"),
        UniqueConstraint("tenant_id", "key_hash", name="uq_idempotency_tenant_key_hash"),
        Index("ix_idempotency_expires_at", "expires_at"),
    )

    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Collection(TenantRow, Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_collections_tenant_id_id"),
        UniqueConstraint("tenant_id", "name", name="uq_collections_tenant_name"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Document(TenantRow, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "collection_id"],
            ["collections.tenant_id", "collections.id"],
            ondelete="CASCADE",
        ),
        Index("ix_documents_tenant_collection_created", "tenant_id", "collection_id", "created_at"),
    )

    collection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="upload")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chunk(TenantRow, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_chunks_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "collection_id"],
            ["collections.tenant_id", "collections.id"],
            ondelete="CASCADE",
        ),
        Index("ix_chunks_fts", "search_vector", postgresql_using="gin"),
        Index("ix_chunks_metadata", "metadata", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tenant_collection", "tenant_id", "collection_id"),
    )

    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    collection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR())
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english'::regconfig, content)", persisted=True),
        nullable=False,
    )
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(TenantRow, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_jobs_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
        ),
        Index("ix_jobs_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Conversation(TenantRow, Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id_id"),)

    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False, server_default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(TenantRow, Base):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        Index("ix_messages_tenant_conversation_created", "tenant_id", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QueryLog(TenantRow, Base):
    __tablename__ = "query_logs"
    __table_args__ = (
        Index("ix_query_logs_tenant_created", "tenant_id", "created_at"),
    )

    key_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    feedback: Mapped[str | None] = mapped_column(String(16))


TENANT_TABLES = (
    "users",
    "api_keys",
    "idempotency_records",
    "collections",
    "documents",
    "chunks",
    "jobs",
    "conversations",
    "messages",
    "query_logs",
)
