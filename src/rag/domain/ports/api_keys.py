"""Persistence port for tenant-scoped machine credentials."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from rag.domain.auth import ApiKeyRecord, Principal, Scope


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


class ApiKeyApplication(Protocol):
    """Application service contract consumed by the HTTP adapter."""

    async def authenticate(self, token: str) -> Principal: ...

    async def issue(
        self,
        actor: Principal,
        name: str,
        scopes: frozenset[Scope],
        expires_at: datetime | None,
        idempotency_key: str,
    ) -> tuple[ApiKeyRecord, str]: ...

    async def list_keys(
        self, tenant_id: UUID, cursor: UUID | None, limit: int
    ) -> list[ApiKeyRecord]: ...

    async def revoke(self, tenant_id: UUID, key_id: UUID) -> bool: ...
