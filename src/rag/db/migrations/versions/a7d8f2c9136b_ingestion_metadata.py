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
        "chunks", sa.Column("trust_level", sa.String(length=16), server_default="untrusted", nullable=False)
    )
    op.add_column("chunks", sa.Column("embedding_model", sa.String(length=120), nullable=True))
    op.add_column("chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("stage", sa.String(length=80), nullable=True))
    op.add_column(
        "jobs", sa.Column("retryable", sa.Boolean(), server_default=sa.false(), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("jobs", "retryable")
    op.drop_column("jobs", "stage")
    op.drop_column("chunks", "embedding_dimensions")
    op.drop_column("chunks", "embedding_model")
    op.drop_column("chunks", "quarantined")
    op.drop_column("chunks", "trust_level")
    op.drop_column("documents", "page_count")
    op.drop_column("documents", "size_bytes")
    op.drop_column("documents", "storage_key")
