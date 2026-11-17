"""Persistence operations for authenticated web workspace features."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID



class WebRepository(Protocol):
    """Tenant-bound persistence used by conversations, collections and admin views."""

    async def list_collections(
        self, tenant_id: UUID, cursor: UUID | None, limit: int, search: str | None
    ) -> tuple[list[dict[str, object]], UUID | None]: ...

    async def create_collection(
        self, tenant_id: UUID, name: str, description: str | None
    ) -> dict[str, object]: ...

    async def get_collection(self, tenant_id: UUID, collection_id: UUID) -> dict[str, object] | None: ...

    async def update_collection(
        self, tenant_id: UUID, collection_id: UUID, values: dict[str, object]
    ) -> dict[str, object] | None: ...

    async def delete_collection(self, tenant_id: UUID, collection_id: UUID) -> bool: ...

    async def create_conversation(
        self, tenant_id: UUID, key_id: UUID, title: str
    ) -> dict[str, object]: ...

    async def list_conversations(
        self,
        tenant_id: UUID,
        key_id: UUID,
        cursor: UUID | None,
        limit: int,
        search: str | None,
    ) -> tuple[list[dict[str, object]], UUID | None]: ...

    async def get_conversation(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID
    ) -> dict[str, object] | None: ...

    async def update_conversation(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID, values: dict[str, object]
    ) -> dict[str, object] | None: ...

    async def delete_conversation(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID
    ) -> bool: ...

    async def list_messages(
        self, tenant_id: UUID, key_id: UUID, conversation_id: UUID, cursor: UUID | None, limit: int
    ) -> tuple[list[dict[str, object]], UUID | None] | None: ...

    async def append_exchange(
        self,
        tenant_id: UUID,
        key_id: UUID,
        conversation_id: UUID,
        question: str,
        answer: str,
        citations: list[dict[str, object]],
        request_id: str,
    ) -> bool: ...

    async def feedback(
        self,
        tenant_id: UUID,
        key_id: UUID,
        request_id: str,
        rating: str,
        reason: str | None,
    ) -> str: ...

    async def usage(self, tenant_id: UUID, since: datetime, until: datetime) -> dict[str, object]: ...

