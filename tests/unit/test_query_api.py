from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from rag.api.main import create_app
from rag.core.config import Settings
from rag.domain.auth import Principal, Role, Scope
from rag.domain.ports.query import CitationRecord, QueryResultRecord
from rag.domain.ports.rate_limiter import RateLimitDecision


class _KeyApplication:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def authenticate(self, token: str) -> Principal:
        del token
        return self.principal


class _Limiter:
    async def consume(
        self, tenant_id: str, key_id: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        del tenant_id, key_id, window_seconds
        return RateLimitDecision(True, limit, limit - 1, 100)


class _Query:
    async def answer(self, **kwargs: object) -> QueryResultRecord:
        return QueryResultRecord(
            answer="The policy allows leave.",
            citations=(
                CitationRecord(
                    "chunk-1", "doc-1", "guide.pdf", 4, "Leave", "Annual leave is available."
                ),
            ),
            refusal=None,
            input_tokens=12,
            output_tokens=7,
            estimated_cost_usd=None,
            request_id=str(kwargs["request_id"]),
        )


def _client(role: Role = Role.VIEWER) -> TestClient:
    principal = Principal(uuid4(), uuid4(), frozenset({Scope.READ}), role)
    app = create_app(
        Settings(app_env="test"),
        api_key_application=_KeyApplication(principal),
        rate_limiter=_Limiter(),
        query_service=_Query(),
    )
    return TestClient(app)


def test_query_json_returns_citations_and_usage() -> None:
    with _client() as client:
        response = client.post(
            "/v1/query",
            headers={"Authorization": "Bearer valid"},
            json={"question": "leave policy?", "collection_ids": [str(uuid4())]},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "The policy allows leave."
    assert payload["citations"][0]["chunk_id"] == "chunk-1"
    assert "estimated_cost_usd" in payload["usage"]


def test_query_sse_obeys_event_order_and_one_terminal_event() -> None:
    with _client() as client:
        response = client.post(
            "/v1/query",
            headers={"Authorization": "Bearer valid"},
            json={"question": "leave policy?", "collection_ids": [str(uuid4())], "stream": True},
        )
    text = response.text
    event_names = [
        line.removeprefix("event: ")
        for line in text.splitlines()
        if line.startswith("event: ")
    ]
    assert response.headers["content-type"].startswith("text/event-stream")
    assert event_names[0] == "retrieval_started"
    assert event_names[1] == "citations"
    assert event_names[-1] == "done"
    assert event_names.count("done") + event_names.count("error") == 1
    assert '"contract_version":"rag.query.v1"' in text


def test_query_rejects_duplicate_collections() -> None:
    collection_id = str(uuid4())
    with _client() as client:
        response = client.post(
            "/v1/query",
            headers={"Authorization": "Bearer valid"},
            json={"question": "leave policy?", "collection_ids": [collection_id, collection_id]},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
