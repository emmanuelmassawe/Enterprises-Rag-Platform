"""Behavior tests for tenant-scoped collection and conversation routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from rag.api.main import create_app
from rag.core.config import Settings
from rag.domain.auth import Principal, Role, Scope
from rag.domain.ports.rate_limiter import RateLimitDecision


class _Keys:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def authenticate(self, _: str) -> Principal:
        return self.principal


class _Limiter:
    async def consume(self, *_: object) -> RateLimitDecision:
        return RateLimitDecision(True, 60, 59, 100)


class _Probe:
    def __init__(self, result: bool = True, fail: bool = False) -> None:
        self.result = result
        self.fail = fail

    async def ping(self) -> bool:
        if self.fail:
            raise RuntimeError("synthetic probe failure")
        return self.result


class _Workspace:
    def __init__(self) -> None:
        self.collection = {"id": str(uuid4()), "name": "Policies"}
        self.conversation = {"id": str(uuid4()), "title": "Policy question"}
        self.feedback_status = "recorded"

    async def list_collections(self, *_: object):
        return [self.collection], UUID(self.collection["id"])

    async def create_collection(self, tenant_id: UUID, name: str, description: str | None):
        return {"tenant_id": str(tenant_id), "name": name, "description": description}

    async def get_collection(self, _: UUID, collection_id: UUID):
        return self.collection if str(collection_id) == self.collection["id"] else None

    async def update_collection(self, _: UUID, collection_id: UUID, values: dict[str, object]):
        if str(collection_id) != self.collection["id"]:
            return None
        return {**self.collection, **values}

    async def delete_collection(self, _: UUID, collection_id: UUID) -> bool:
        return str(collection_id) == self.collection["id"]

    async def create_conversation(self, tenant_id: UUID, key_id: UUID, title: str):
        return {"tenant_id": str(tenant_id), "key_id": str(key_id), "title": title}

    async def list_conversations(self, *_: object):
        return [self.conversation], UUID(self.conversation["id"])

    async def get_conversation(self, _: UUID, __: UUID, conversation_id: UUID):
        return self.conversation if str(conversation_id) == self.conversation["id"] else None

    async def update_conversation(
        self, _: UUID, __: UUID, conversation_id: UUID, values: dict[str, object]
    ):
        if str(conversation_id) != self.conversation["id"]:
            return None
        return {**self.conversation, **values}

    async def delete_conversation(self, _: UUID, __: UUID, conversation_id: UUID) -> bool:
        return str(conversation_id) == self.conversation["id"]

    async def list_messages(
        self, _: UUID, __: UUID, conversation_id: UUID, ___: UUID | None, ____: int
    ):
        if str(conversation_id) != self.conversation["id"]:
            return None
        return ([{"role": "assistant", "content": "Supported."}], None)

    async def append_exchange(self, *_: object) -> bool:
        return True

    async def feedback(self, *_: object) -> str:
        return self.feedback_status

    async def usage(self, _: UUID, since: datetime, until: datetime):
        return {"since": since.isoformat(), "until": until.isoformat(), "query_count": 2}


def _client(
    repository: _Workspace | None = None,
    *,
    probes: tuple[_Probe | None, _Probe | None, _Probe | None] = (None, None, None),
) -> tuple[TestClient, Principal, _Workspace]:
    tenant_id, key_id = uuid4(), uuid4()
    principal = Principal(
        tenant_id, key_id, frozenset({Scope.READ, Scope.WRITE, Scope.ADMIN}), Role.ADMIN
    )
    web = repository or _Workspace()
    app = create_app(
        Settings(app_env="test"),
        api_key_application=_Keys(principal),
        rate_limiter=_Limiter(),
        web_repository=web,
        database_probe=probes[0],
        rate_limiter_probe=probes[1],
        ingestion_queue=probes[2],
    )
    return TestClient(app), principal, web


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer synthetic-test-key"}


def test_collections_crud_and_problem_details() -> None:
    client, _, repository = _client()
    with client:
        listed = client.get("/v1/collections?limit=1&search=policy", headers=_auth())
        assert listed.status_code == 200
        assert listed.json()["page"]["has_more"] is True

        created = client.post(
            "/v1/collections",
            headers=_auth(),
            json={"name": "  Research  ", "description": "Notes"},
        )
        assert created.status_code == 201
        assert created.json()["name"] == "Research"
        assert created.json()["description"] == "Notes"
        assert (
            client.post("/v1/collections", headers=_auth(), json={"name": "   "}).status_code == 422
        )

        collection_id = repository.collection["id"]
        assert client.get(f"/v1/collections/{collection_id}", headers=_auth()).status_code == 200
        assert (
            client.patch(
                f"/v1/collections/{collection_id}", headers=_auth(), json={"name": " Updated "}
            ).json()["name"]
            == "Updated"
        )
        assert client.get(f"/v1/collections/{uuid4()}", headers=_auth()).status_code == 404
        assert (
            client.patch(
                f"/v1/collections/{uuid4()}", headers=_auth(), json={"description": "missing"}
            ).status_code
            == 404
        )
        assert client.delete(f"/v1/collections/{collection_id}", headers=_auth()).status_code == 204
        missing = client.delete(f"/v1/collections/{uuid4()}", headers=_auth())
        assert missing.status_code == 404 and missing.json()["code"] == "not_found"


def test_conversations_history_messages_and_feedback() -> None:
    client, principal, repository = _client()
    request_id = "request-synthetic-001"
    idempotency = "i" * 32
    with client:
        created = client.post("/v1/conversations", headers=_auth(), json={"title": "  New title  "})
        assert created.status_code == 201
        assert created.json()["tenant_id"] == str(principal.tenant_id)
        assert created.json()["key_id"] == str(principal.key_id)
        assert (
            client.post("/v1/conversations", headers=_auth(), json={"title": " "}).status_code
            == 422
        )

        conversation_id = repository.conversation["id"]
        assert client.get("/v1/conversations?limit=1", headers=_auth()).json()["page"]["has_more"]
        assert (
            client.get(f"/v1/conversations/{conversation_id}", headers=_auth()).status_code == 200
        )
        assert (
            client.patch(
                f"/v1/conversations/{conversation_id}", headers=_auth(), json={"pinned": True}
            ).json()["pinned"]
            is True
        )
        assert (
            client.patch(
                f"/v1/conversations/{uuid4()}", headers=_auth(), json={"title": "Missing"}
            ).status_code
            == 404
        )
        assert (
            client.get(f"/v1/conversations/{conversation_id}/messages", headers=_auth()).json()[
                "items"
            ][0]["role"]
            == "assistant"
        )
        assert (
            client.get(f"/v1/conversations/{uuid4()}/messages", headers=_auth()).status_code == 404
        )
        assert (
            client.delete(f"/v1/conversations/{conversation_id}", headers=_auth()).status_code
            == 204
        )
        assert client.delete(f"/v1/conversations/{uuid4()}", headers=_auth()).status_code == 404

        feedback = client.post(
            "/v1/feedback",
            headers={**_auth(), "Idempotency-Key": idempotency},
            json={"request_id": request_id, "rating": "up"},
        )
        assert feedback.status_code == 202 and feedback.json()["status"] == "recorded"
        repository.feedback_status = "same"
        assert (
            client.post(
                "/v1/feedback",
                headers={**_auth(), "Idempotency-Key": idempotency},
                json={"request_id": request_id, "rating": "up"},
            ).json()["status"]
            == "same"
        )
        repository.feedback_status = "conflict"
        assert (
            client.post(
                "/v1/feedback",
                headers={**_auth(), "Idempotency-Key": idempotency},
                json={"request_id": request_id, "rating": "up"},
            ).status_code
            == 409
        )
        repository.feedback_status = "not_found"
        assert (
            client.post(
                "/v1/feedback",
                headers={**_auth(), "Idempotency-Key": idempotency},
                json={"request_id": request_id, "rating": "down"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/v1/feedback",
                headers={**_auth(), "Idempotency-Key": "bad"},
                json={"request_id": request_id, "rating": "up"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/feedback",
                headers={**_auth(), "Idempotency-Key": idempotency},
                json={"request_id": request_id, "rating": "middle"},
            ).status_code
            == 422
        )


def test_admin_usage_validation_and_dependency_status() -> None:
    probes = (_Probe(), _Probe(False), _Probe(fail=True))
    client, _, _ = _client(probes=probes)
    now = datetime.now(UTC)
    with client:
        usage = client.get("/v1/admin/usage", headers=_auth())
        assert usage.status_code == 200 and usage.json()["query_count"] == 2
        assert (
            client.get(
                "/v1/admin/usage",
                params={"since": "2026-01-01T00:00:00", "until": "2026-01-02T00:00:00"},
                headers=_auth(),
            ).status_code
            == 422
        )
        too_long = client.get(
            "/v1/admin/usage",
            params={"since": (now - timedelta(days=400)).isoformat(), "until": now.isoformat()},
            headers=_auth(),
        )
        assert too_long.status_code == 422
        status = client.get("/v1/admin/status", headers=_auth())
        assert status.json() == {
            "status": "degraded",
            "checks": {
                "api": "ok",
                "database": "ok",
                "rate_limiter": "unavailable",
                "ingestion_queue": "unavailable",
            },
        }


def test_workspace_storage_missing_returns_problem_details() -> None:
    client, _, _ = _client()
    client.app.state.web_repository = None
    with client:
        response = client.get("/v1/collections", headers=_auth())
    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
