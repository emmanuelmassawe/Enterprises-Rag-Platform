"""Adapter behavior tests for FR-AUTH-001 tenant-scoped API-key persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from rag.adapters.postgres.api_keys import PostgresApiKeyStore
from rag.adapters.postgres.models import ApiKey
from rag.db.session import Database
from rag.domain.auth import ApiKeyRecord, IdempotencyConflict, Scope


class _Result:
    def __init__(self, value: UUID | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> UUID | None:
        return self.value


class _Session:
    def __init__(self, row: ApiKey) -> None:
        self.row = row
        self.created: list[Any] = []
        self.claim: UUID | None = uuid4()
        self.revoked: UUID | None = row.id
        self.executions = 0
        self.scalar_calls = 0

    async def scalar(self, _: Any) -> ApiKey | UUID | None:
        self.scalar_calls += 1
        return self.row if self.scalar_calls == 1 else self.revoked

    async def scalars(self, _: Any) -> _Rows:
        return _Rows([self.row])

    async def execute(self, _: Any) -> _Result:
        self.executions += 1
        return _Result(self.claim if self.executions == 2 else self.revoked)

    def add(self, value: Any) -> None:
        self.created.append(value)


class _Rows:
    def __init__(self, values: list[ApiKey]) -> None:
        self.values = values

    def all(self) -> list[ApiKey]:
        return self.values


class _Database:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.tenants: list[UUID] = []

    @asynccontextmanager
    async def tenant_session(self, tenant_id: UUID) -> AsyncIterator[_Session]:
        self.tenants.append(tenant_id)
        yield self.session


def _row(tenant_id: UUID, key_id: UUID) -> ApiKey:
    return ApiKey(
        id=key_id,
        tenant_id=tenant_id,
        name="test key",
        secret_hash="a" * 64,
        scopes=["read"],
        created_at=datetime.now(UTC),
    )


def _record(tenant_id: UUID, key_id: UUID) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=key_id,
        tenant_id=tenant_id,
        name="new key",
        secret_hash="b" * 64,
        scopes=frozenset({Scope.READ}),
        created_at=datetime.now(UTC),
        expires_at=None,
    )


@pytest.mark.asyncio
async def test_req_fr_auth_001_postgres_store_uses_tenant_scope_and_maps_rows() -> None:
    tenant_id, key_id = uuid4(), uuid4()
    session = _Session(_row(tenant_id, key_id))
    database = _Database(session)
    store = PostgresApiKeyStore(cast(Database, database))

    found = await store.get(tenant_id, key_id)
    page = await store.list(tenant_id, None, 20)
    revoked = await store.revoke(tenant_id, key_id)
    await store.touch_last_used(tenant_id, key_id)

    assert found is not None and found.id == key_id and found.scopes == {Scope.READ}
    assert [item.id for item in page] == [key_id]
    assert revoked
    assert database.tenants == [tenant_id] * 4


@pytest.mark.asyncio
async def test_req_fr_auth_001_postgres_store_claims_idempotency_before_key_insert() -> None:
    tenant_id, key_id = uuid4(), uuid4()
    session = _Session(_row(tenant_id, key_id))
    database = _Database(session)
    store = PostgresApiKeyStore(cast(Database, database))

    await store.create(_record(tenant_id, key_id), "c" * 64, "d" * 64)

    assert len(session.created) == 1
    assert session.created[0].id == key_id
    assert session.executions == 2


@pytest.mark.asyncio
async def test_req_fr_auth_001_postgres_store_rejects_reused_idempotency_claim() -> None:
    tenant_id, key_id = uuid4(), uuid4()
    session = _Session(_row(tenant_id, key_id))
    session.claim = None
    store = PostgresApiKeyStore(cast(Database, _Database(session)))

    with pytest.raises(IdempotencyConflict):
        await store.create(_record(tenant_id, key_id), "c" * 64, "d" * 64)
    assert session.created == []


@pytest.mark.asyncio
async def test_req_fr_auth_001_postgres_store_reports_missing_key_revoke() -> None:
    tenant_id, key_id = uuid4(), uuid4()
    session = _Session(_row(tenant_id, key_id))
    session.revoked = None
    session.scalar_calls = 1
    store = PostgresApiKeyStore(cast(Database, _Database(session)))

    assert not await store.revoke(tenant_id, key_id)
