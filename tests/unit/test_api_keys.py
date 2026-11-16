"""Behavior tests for FR-AUTH-001 and API-key lifecycle endpoints."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from rag.adapters.redis.rate_limiter import MemoryRateLimiter
from rag.api.main import create_app
from rag.core.config import Settings
from rag.domain.auth import ApiKeyRecord, IdempotencyConflict, InvalidCredential, Scope
from rag.services.api_keys import ApiKeyService, parse_token


class FakeKeyStore:
    """In-memory port fake for API-key behavior tests."""

    def __init__(self) -> None:
        self.records: dict[tuple[UUID, UUID], ApiKeyRecord] = {}
        self.idempotency: dict[tuple[UUID, str], str] = {}

    async def get(self, tenant_id: UUID, key_id: UUID) -> ApiKeyRecord | None:
        return self.records.get((tenant_id, key_id))

    async def create(
        self, record: ApiKeyRecord, idempotency_hash: str, request_digest: str
    ) -> None:
        idempotency_key = (record.tenant_id, idempotency_hash)
        if idempotency_key in self.idempotency:
            raise IdempotencyConflict("already issued")
        self.idempotency[idempotency_key] = request_digest
        self.records[(record.tenant_id, record.id)] = record

    async def list(self, tenant_id: UUID, cursor: UUID | None, limit: int) -> list[ApiKeyRecord]:
        result = [row for (owner, _), row in self.records.items() if owner == tenant_id]
        result.sort(key=lambda item: item.id.int, reverse=True)
        if cursor is not None:
            result = [row for row in result if row.id < cursor]
        return result[:limit]

    async def revoke(self, tenant_id: UUID, key_id: UUID) -> bool:
        identity = (tenant_id, key_id)
        record = self.records.get(identity)
        if record is None:
            return False
        if record.revoked_at is None:
            self.records[identity] = replace(record, revoked_at=datetime.now(UTC))
        return True

    async def touch_last_used(self, tenant_id: UUID, key_id: UUID) -> None:
        identity = (tenant_id, key_id)
        self.records[identity] = replace(self.records[identity], last_used_at=datetime.now(UTC))


class HealthyProbe:
    async def ping(self) -> bool:
        return True


def _admin_credential(store: FakeKeyStore) -> str:
    tenant_id = uuid4()
    key_id = uuid4()
    secret = "synthetic-secret-for-tests-0123456789"  # noqa: S105 - synthetic test credential
    store.records[(tenant_id, key_id)] = ApiKeyRecord(
        id=key_id,
        tenant_id=tenant_id,
        name="bootstrap test key",
        secret_hash=hashlib.sha256(secret.encode("ascii")).hexdigest(),
        scopes=frozenset({Scope.ADMIN}),
        created_at=datetime.now(UTC),
        expires_at=None,
    )
    return f"rag.{tenant_id}.{key_id}.{secret}"


def _client(store: FakeKeyStore, *, limit: int = 60) -> TestClient:
    settings = Settings(
        app_env="test",
        rate_limit_requests=limit,
        rate_limit_memory_fallback_requests=limit,
    )
    return TestClient(
        create_app(
            settings,
            api_key_application=ApiKeyService(store),
            rate_limiter=MemoryRateLimiter(),
            database_probe=HealthyProbe(),
            rate_limiter_probe=HealthyProbe(),
        )
    )


def test_req_fr_auth_001_api_key_is_hashed_and_returned_once() -> None:
    store = FakeKeyStore()
    admin_token = _admin_credential(store)
    tenant_text = admin_token.split(".")[1]
    client = _client(store)
    idempotency_key = "I" * 32

    response = client.post(
        "/v1/admin/api-keys",
        headers={"Authorization": f"Bearer {admin_token}", "Idempotency-Key": idempotency_key},
        json={"name": "reporting", "scopes": ["read"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["key"]["name"] == "reporting"
    assert body["key"]["scopes"] == ["read"]
    assert body["secret"].startswith(f"rag.{tenant_text}.")
    issued = next(record for record in store.records.values() if record.name == "reporting")
    assert body["secret"].split(".")[-1] not in issued.secret_hash

    replay = client.post(
        "/v1/admin/api-keys",
        headers={"Authorization": f"Bearer {admin_token}", "Idempotency-Key": idempotency_key},
        json={"name": "reporting", "scopes": ["read"]},
    )
    assert replay.status_code == 409
    assert len(store.records) == 2


def test_req_fr_auth_001_malformed_non_ascii_secret_is_rejected_cleanly() -> None:
    with pytest.raises(InvalidCredential):
        parse_token(f"rag.{uuid4()}.{uuid4()}.{'é' * 40}")


def test_req_fr_auth_001_invalid_and_insufficient_credentials_are_denied() -> None:
    store = FakeKeyStore()
    _admin_credential(store)
    client = _client(store)

    missing = client.get("/v1/admin/api-keys")
    invalid = client.get("/v1/admin/api-keys", headers={"Authorization": "Bearer invalid"})
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "authentication_required"

    tenant_id = uuid4()
    key_id = uuid4()
    secret = "read-only-synthetic-secret-0123456789"  # noqa: S105 - synthetic test credential
    store.records[(tenant_id, key_id)] = ApiKeyRecord(
        id=key_id,
        tenant_id=tenant_id,
        name="reader",
        secret_hash=hashlib.sha256(secret.encode("ascii")).hexdigest(),
        scopes=frozenset({Scope.READ}),
        created_at=datetime.now(UTC),
        expires_at=None,
    )
    denied = client.get(
        "/v1/admin/api-keys", headers={"Authorization": f"Bearer rag.{tenant_id}.{key_id}.{secret}"}
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"


def test_req_fr_auth_001_revoke_and_expiry_invalidate_credentials() -> None:
    store = FakeKeyStore()
    token = _admin_credential(store)
    client = _client(store)
    _, tenant_text, key_text, _ = token.split(".")

    revoked = client.delete(
        f"/v1/admin/api-keys/{key_text}", headers={"Authorization": f"Bearer {token}"}
    )
    denied = client.get("/v1/admin/api-keys", headers={"Authorization": f"Bearer {token}"})
    assert revoked.status_code == 204
    assert denied.status_code == 401
    assert UUID(tenant_text)

    expired_tenant, expired_id = uuid4(), uuid4()
    expired_secret = "expired-synthetic-secret-0123456789"  # noqa: S105 - synthetic test credential
    store.records[(expired_tenant, expired_id)] = ApiKeyRecord(
        id=expired_id,
        tenant_id=expired_tenant,
        name="expired",
        secret_hash=hashlib.sha256(expired_secret.encode("ascii")).hexdigest(),
        scopes=frozenset({Scope.ADMIN}),
        created_at=datetime.now(UTC),
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    expired = client.get(
        "/v1/admin/api-keys",
        headers={"Authorization": f"Bearer rag.{expired_tenant}.{expired_id}.{expired_secret}"},
    )
    assert expired.status_code == 401


def test_req_fr_auth_004_rate_limit_returns_retry_after_and_headers() -> None:
    store = FakeKeyStore()
    token = _admin_credential(store)
    client = _client(store, limit=1)

    first = client.get("/v1/admin/api-keys", headers={"Authorization": f"Bearer {token}"})
    second = client.get("/v1/admin/api-keys", headers={"Authorization": f"Bearer {token}"})

    assert first.status_code == 200
    assert first.headers["ratelimit-limit"] == "1"
    assert second.status_code == 429
    assert second.headers["retry-after"]
    assert second.json()["code"] == "rate_limited"
