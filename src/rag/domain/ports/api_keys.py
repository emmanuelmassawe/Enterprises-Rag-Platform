"""Persistence port for tenant-scoped machine credentials."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from rag.domain.auth import ApiKeyRecord


class ApiKeyStore(Protocol):
    """Operations required by API-key authentication and lifecycle endpoints."""

    async def get(self, tenant_id: UUID, key_id: UUID) -> ApiKeyRecord | None: ...

    async def create(
        self, record: ApiKeyRecord, idempotency_hash: str, request_digest: str
    ) -> None: ...

    async def list(
        self, tenant_id: UUID, cursor: UUID | None, limit: int
    ) -> list[ApiKeyRecord]: ...

    async def revoke(self, tenant_id: UUID, key_id: UUID) -> bool: ...

    async def touch_last_used(self, tenant_id: UUID, key_id: UUID) -> None: ...
