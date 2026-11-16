"""Transaction context behavior tests for the tenant-bound database adapter."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rag.db.session import Database


class _Session:
    def __init__(self) -> None:
        self.statements: list[tuple[object, dict[str, str] | None]] = []

    async def execute(self, statement: object, params: dict[str, str] | None = None) -> None:
        self.statements.append((statement, params))


class _SessionContext:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def __aenter__(self) -> _Session:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


class _TransactionContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.mark.asyncio
async def test_req_fr_auth_003_database_sets_transaction_local_identity(monkeypatch) -> None:
    tenant_id, principal_id = uuid4(), uuid4()
    database = Database("postgresql+asyncpg://rag_runtime@localhost/db")

    class ContextualSession(_Session):
        def begin(self) -> _TransactionContext:
            return _TransactionContext()

    session = ContextualSession()
    monkeypatch.setattr(database, "_sessions", lambda: _SessionContext(session))

    async with database.tenant_session(tenant_id, principal_id) as actual:
        assert actual is session
    await database.dispose()

    assert len(session.statements) == 2
    assert session.statements[0][1] == {"tenant_id": str(tenant_id)}
    assert session.statements[1][1] == {"principal_id": str(principal_id)}


def test_req_fr_auth_003_database_rejects_non_asyncpg_url() -> None:
    with pytest.raises(ValueError, match=r"postgresql\+asyncpg"):
        Database("postgresql://localhost/db")
