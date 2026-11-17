"""Add API-key owned conversations, pinning, and feedback reasons.

Revision ID: e86a1d7c4b29
Revises: b4c2e9137f60
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e86a1d7c4b29"
down_revision: str | tuple[str, str] | None = ("b4c2e9137f60", "c51b6d27e940")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("conversations", "owner_id", existing_type=postgresql.UUID(), nullable=True)
    op.add_column("conversations", sa.Column("owner_key_id", postgresql.UUID(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_foreign_key(
        "fk_conversations_owner_key",
        "conversations",
        "api_keys",
        ["tenant_id", "owner_key_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_conversations_single_owner",
        "conversations",
        "(owner_id IS NOT NULL AND owner_key_id IS NULL) OR "
        "(owner_id IS NULL AND owner_key_id IS NOT NULL)",
    )
    op.create_index(
        "ix_conversations_tenant_owner_key_updated",
        "conversations",
        ["tenant_id", "owner_key_id", "updated_at", "id"],
    )
    op.add_column("query_logs", sa.Column("feedback_reason", sa.String(length=1000)))


def downgrade() -> None:
    op.drop_column("query_logs", "feedback_reason")
    op.drop_index("ix_conversations_tenant_owner_key_updated", table_name="conversations")
    op.drop_constraint("ck_conversations_single_owner", "conversations", type_="check")
    op.drop_constraint("fk_conversations_owner_key", "conversations", type_="foreignkey")
    op.drop_column("conversations", "pinned")
    op.drop_column("conversations", "owner_key_id")
    op.alter_column("conversations", "owner_id", existing_type=postgresql.UUID(), nullable=False)
