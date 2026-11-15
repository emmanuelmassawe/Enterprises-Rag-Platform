"""Async SQLAlchemy engine and tenant-bound transaction management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Owns a bounded async connection pool and transaction-local tenant context."""

    def __init__(self, database_url: str, pool_size: int = 5, max_overflow: int = 5) -> None:
        if not database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=5,
            pool_recycle=300,
            pool_pre_ping=True,
            connect_args={"timeout": 3, "command_timeout": 10},
        )
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def tenant_session(
        self, tenant_id: UUID, principal_id: UUID | None = None
    ) -> AsyncIterator[AsyncSession]:
        """Bind tenant and principal settings locally for exactly one transaction."""
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            if principal_id is not None:
                await session.execute(
                    text("SELECT set_config('app.principal_id', :principal_id, true)"),
                    {"principal_id": str(principal_id)},
                )
            yield session

    async def ping(self) -> bool:
        """Check database connectivity with a hard timeout from the driver."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True

    async def dispose(self) -> None:
        """Close idle and checked-in pooled database connections."""
        await self.engine.dispose()
