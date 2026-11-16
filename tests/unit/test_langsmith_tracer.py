from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from rag.adapters.tracing import langsmith


class _FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.options = kwargs
        self.runs: list[dict[str, Any]] = []

    def create_run(self, **kwargs: Any) -> None:
        self.runs.append(kwargs)

    def flush(self) -> None:
        return None


def test_langsmith_export_uses_empty_content_and_nested_allowlisted_metadata(
    monkeypatch: Any,
) -> None:
    client = _FakeClient()

    def create_client(**kwargs: Any) -> _FakeClient:
        client.options = kwargs
        return client

    monkeypatch.setattr(langsmith, "Client", create_client)
    tracer = langsmith.LangSmithTracer("synthetic-test-key", "rag-test")
    assert client.options["hide_inputs"] is True
    assert client.options["hide_outputs"] is True
    assert client.options["timeout_ms"] == 1_000

    metadata = {
        "request_id": "req-test",
        "trace_id": "0123456789abcdef0123456789abcdef",
        "tenant_ref": "a" * 16,
        "environment": "test",
        "model": "synthetic-model",
        "prompt_version": "query-v1",
        "input_tokens": 5,
        "output_tokens": 2,
        "duration_ms": 10,
        "outcome": "answered",
        "question": "private question text",
        "secret": "do-not-export",
    }
    tracer._export(metadata)

    assert len(client.runs) == 5
    root = client.runs[0]
    assert root["name"] == "rag.query"
    assert root["inputs"] == root["outputs"] == {}
    root_id = root["id"]
    assert isinstance(root_id, UUID)
    for child in client.runs[1:]:
        assert child["parent_run_id"] == root_id
        assert child["inputs"] == child["outputs"] == {}
        serialized = str(child["extra"])
        assert "private question text" not in serialized
        assert "do-not-export" not in serialized
    assert all(isinstance(run["start_time"], datetime) for run in client.runs)


def test_langsmith_request_queue_drops_unapproved_fields(monkeypatch: Any) -> None:
    client = _FakeClient()

    def create_client(**kwargs: Any) -> _FakeClient:
        client.options = kwargs
        return client

    monkeypatch.setattr(langsmith, "Client", create_client)
    tracer = langsmith.LangSmithTracer("synthetic-test-key", "rag-test")
    tracer.record_run({"request_id": "req-safe", "question": "raw content"})
    queued = tracer._queue.get_nowait()
    assert queued == {"request_id": "req-safe"}
