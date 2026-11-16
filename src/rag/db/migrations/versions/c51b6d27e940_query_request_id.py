"""Add request correlation to query audit rows.

Revision ID: c51b6d27e940
Revises: b4c2e9137f60
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c51b6d27e940"
down_revision: str | None = "b4c2e9137f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("query_logs", sa.Column("request_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("query_logs", "request_id")
