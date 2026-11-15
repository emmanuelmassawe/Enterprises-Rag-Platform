"""SQLAlchemy API-key store; each query runs under forced tenant RLS."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from rag.adapters.postgres.models import ApiKey
from rag.db.session import Database
from rag.domain.auth import ApiKeyRecord, Scope
from rag.domain.ports.api_keys import ApiKeyStore


def _record(row: ApiKey) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        secret_hash=row.secret_hash,
        scopes=frozenset(Scope(value) for value in row.scopes),
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


class PostgresApiKeyStore(ApiKeyStore):
    """Persist and resolve credentials without exposing stored secret material."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(self, tenant_id: UUID, key_id: UUID) -> ApiKeyRecord | None:
        async with self._database.tenant_session(tenant_id) as session:
            row = await session.scalar(
                select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.id == key_id)
            )
            return _record(row) if row is not None else None

    async def create(self, record: ApiKeyRecord) -> None:
        async with self._database.tenant_session(record.tenant_id) as session:
            session.add(
                ApiKey(
                    id=record.id,
                    tenant_id=record.tenant_id,
                    name=record.name,
                    secret_hash=record.secret_hash,
                    scopes=sorted(scope.value for scope in record.scopes),
                    created_at=record.created_at,
                    expires_at=record.expires_at,
                )
            )

    async def list(self, tenant_id: UUID, cursor: UUID | None, limit: int) -> list[ApiKeyRecord]:
        statement = select(ApiKey).where(ApiKey.tenant_id == tenant_id)
        if cursor is not None:
            statement = statement.where(ApiKey.id < cursor)
        statement = statement.order_by(ApiKey.id.desc()).limit(limit)
        async with self._database.tenant_session(tenant_id) as session:
            rows = (await session.scalars(statement)).all()
        return [_record(row) for row in rows]

    async def revoke(self, tenant_id: UUID, key_id: UUID) -> bool:
        async with self._database.tenant_session(tenant_id) as session:
            result = await session.execute(
                update(ApiKey)
                .where(ApiKey.tenant_id == tenant_id, ApiKey.id == key_id)
                .values(revoked_at=ApiKey.revoked_at if ApiKey.revoked_at.is_not(None) else datetime.now(UTC))
            )
            return bool(result.rowcount)

    async def touch_last_used(self, tenant_id: UUID, key_id: UUID) -> None:
        async with self._database.tenant_session(tenant_id) as session:
            await session.execute(
                update(ApiKey)
                .where(ApiKey.tenant_id == tenant_id, ApiKey.id == key_id)
                .values(last_used_at=datetime.now(UTC))
            )
