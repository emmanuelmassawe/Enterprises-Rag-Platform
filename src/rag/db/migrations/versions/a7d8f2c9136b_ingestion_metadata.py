"""Add private-object and bounded-ingestion metadata.

Revision ID: a7d8f2c9136b
Revises: d050ab363dc1
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d8f2c9136b"
down_revision: str | None = "d050ab363dc1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("storage_key", sa.String(length=512), server_default="", nullable=False),
    )
    op.add_column(
        "documents", sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("documents", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column(
        "chunks", sa.Column("quarantined", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column(
        "chunks",
        sa.Column(
            "quarantine_status", sa.String(length=16), server_default="clear", nullable=False
        ),
    )
    op.add_column(
        "chunks",
        sa.Column("trust_level", sa.String(length=16), server_default="untrusted", nullable=False),
    )
    op.add_column("chunks", sa.Column("embedding_model", sa.String(length=120), nullable=True))
    op.add_column("chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("stage", sa.String(length=80), nullable=True))
    op.add_column(
        "jobs", sa.Column("retryable", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.create_table(
        "quarantine_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("actor_key_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("idempotency_hash", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chunk_id"], ["chunks.tenant_id", "chunks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_key_id"],
            ["api_keys.tenant_id", "api_keys.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_quarantine_decisions_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_hash", name="uq_quarantine_decisions_tenant_key_hash"
        ),
    )
    op.create_index(
        "ix_quarantine_tenant_created", "quarantine_decisions", ["tenant_id", "created_at"]
    )
    op.execute('ALTER TABLE "quarantine_decisions" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "quarantine_decisions" FORCE ROW LEVEL SECURITY')
    op.execute(
        "CREATE POLICY tenant_isolation_quarantine_decisions ON quarantine_decisions "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE quarantine_decisions TO rag_runtime")


def downgrade() -> None:
    op.drop_column("jobs", "retryable")
    op.drop_column("jobs", "stage")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_quarantine_decisions ON quarantine_decisions"
    )
    op.drop_index("ix_quarantine_tenant_created", table_name="quarantine_decisions")
    op.drop_table("quarantine_decisions")
    op.drop_column("chunks", "embedding_dimensions")
    op.drop_column("chunks", "embedding_model")
    op.drop_column("chunks", "quarantined")
    op.drop_column("chunks", "quarantine_status")
    op.drop_column("chunks", "trust_level")
    op.drop_column("documents", "page_count")
    op.drop_column("documents", "size_bytes")
    op.drop_column("documents", "storage_key")
