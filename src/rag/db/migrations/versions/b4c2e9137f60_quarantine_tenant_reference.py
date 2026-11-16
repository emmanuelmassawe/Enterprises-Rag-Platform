"""Add the tenant parent reference to quarantine audit rows.

Revision ID: b4c2e9137f60
Revises: a7d8f2c9136b
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b4c2e9137f60"
down_revision: str | None = "a7d8f2c9136b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_quarantine_decisions_tenant_id_tenants",
        "quarantine_decisions",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quarantine_decisions_tenant_id_tenants",
        "quarantine_decisions",
        type_="foreignkey",
    )
