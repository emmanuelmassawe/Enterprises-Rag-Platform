"""API-key lifecycle and bearer credential verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from rag.domain.auth import (
    ApiKeyCredentials,
    ApiKeyRecord,
    InvalidCredential,
    InvalidKeyGrant,
    Principal,
    Scope,
    role_for_scopes,
)
from rag.domain.ports.api_keys import ApiKeyStore

API_KEY_FORMAT_PREFIX = "rag"


def parse_token(token: str) -> ApiKeyCredentials:
    """Parse `rag.<tenant UUID>.<key UUID>.<random secret>` without trusting it."""
    parts = token.split(".", maxsplit=3)
    if len(parts) != 4 or parts[0] != API_KEY_FORMAT_PREFIX or len(parts[3]) < 32:
        raise InvalidCredential("invalid bearer credential")
    try:
        return ApiKeyCredentials(UUID(parts[1]), UUID(parts[2]), parts[3])
    except ValueError as exc:
        raise InvalidCredential("invalid bearer credential") from exc


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


class ApiKeyService:
    """Implements hashed API-key validation and tenant key lifecycle rules."""

    def __init__(self, store: ApiKeyStore) -> None:
        self._store = store

    async def authenticate(self, token: str) -> Principal:
        """Resolve a bearer key and return only validated tenant and scope claims."""
        credentials = parse_token(token)
        record = await self._store.get(credentials.tenant_id, credentials.key_id)
        if record is None:
            raise InvalidCredential("invalid bearer credential")
        supplied_digest = _digest(credentials.secret)
        if not hmac.compare_digest(supplied_digest, record.secret_hash):
            raise InvalidCredential("invalid bearer credential")
        now = datetime.now(UTC)
        if record.revoked_at is not None or (
            record.expires_at is not None and record.expires_at <= now
        ):
            raise InvalidCredential("invalid bearer credential")
        await self._store.touch_last_used(record.tenant_id, record.id)
        return Principal(
            tenant_id=record.tenant_id,
            key_id=record.id,
            scopes=record.scopes,
            role=role_for_scopes(record.scopes),
        )

    async def issue(
        self,
        actor: Principal,
        name: str,
        scopes: frozenset[Scope],
        expires_at: datetime | None,
        idempotency_key: str,
    ) -> tuple[ApiKeyRecord, str]:
        """Create a tenant key, returning its random secret exactly to this caller."""
        if Scope.ADMIN not in actor.scopes:
            raise InvalidKeyGrant("admin scope is required")
        if not name.strip() or len(name) > 120 or not scopes:
            raise InvalidKeyGrant("key name and at least one scope are required")
        if not all(actor.allows(scope) for scope in scopes):
            raise InvalidKeyGrant("requested scopes exceed caller authority")
        now = datetime.now(UTC)
        if expires_at is not None and expires_at <= now:
            raise InvalidKeyGrant("expiration must be in the future")
        key_id = uuid4()
        secret = secrets.token_urlsafe(32)
        record = ApiKeyRecord(
            id=key_id,
            tenant_id=actor.tenant_id,
            name=name.strip(),
            secret_hash=_digest(secret),
            scopes=scopes,
            created_at=now,
            expires_at=expires_at,
        )
        idempotency_hash = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()
        request_digest = hashlib.sha256(
            (
                f"{name.strip()}\n{','.join(sorted(scope.value for scope in scopes))}\n{expires_at}"
            ).encode()
        ).hexdigest()
        await self._store.create(record, idempotency_hash, request_digest)
        token = f"{API_KEY_FORMAT_PREFIX}.{actor.tenant_id}.{key_id}.{secret}"
        return record, token

    async def list_keys(
        self, tenant_id: UUID, cursor: UUID | None, limit: int
    ) -> list[ApiKeyRecord]:
        """List bounded metadata in a stable UUID keyset order."""
        return await self._store.list(tenant_id, cursor, limit)

    async def revoke(self, tenant_id: UUID, key_id: UUID) -> bool:
        """Revoke a tenant's key; repeated revocation remains successful."""
        return await self._store.revoke(tenant_id, key_id)
