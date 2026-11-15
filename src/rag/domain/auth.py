"""Tenant and API-key identity types shared by transport and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class Scope(StrEnum):
    """Machine credential permissions from the approved API contract."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class Role(StrEnum):
    """Effective tenant role represented by a machine credential."""

    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


class IdempotencyConflict(ValueError):
    """An idempotency key has been used already and cannot issue a second secret."""


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated, tenant-bound caller context."""

    tenant_id: UUID
    key_id: UUID
    scopes: frozenset[Scope]
    role: Role

    def allows(self, required: Scope) -> bool:
        """Admin credentials imply read/write access; other scopes stay explicit."""
        return Scope.ADMIN in self.scopes or required in self.scopes


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    """Persistable API key metadata; raw credentials are never part of this type."""

    id: UUID
    tenant_id: UUID
    name: str
    secret_hash: str
    scopes: frozenset[Scope]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ApiKeyCredentials:
    """Parsed bearer token components before database verification."""

    tenant_id: UUID
    key_id: UUID
    secret: str


def role_for_scopes(scopes: frozenset[Scope]) -> Role:
    """Map the approved API key scopes to the effective viewer/editor/admin role."""
    if Scope.ADMIN in scopes:
        return Role.ADMIN
    if Scope.WRITE in scopes:
        return Role.EDITOR
    return Role.VIEWER
