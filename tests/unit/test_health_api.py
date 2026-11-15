"""Behavior tests for the initial operational HTTP contract."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rag.api.main import create_app
from rag.core.config import Settings


def test_healthz_reports_liveness_without_dependencies() -> None:
    """Liveness remains independent of databases and queues."""
    client = TestClient(create_app(Settings(app_env="test")))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"].startswith("req_")


def test_readyz_reports_only_dependencies_present_in_milestone_one() -> None:
    """Readiness must not claim external dependency checks before adapters exist."""
    client = TestClient(create_app(Settings(app_env="test")))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"api": "ok"}}


def test_unmatched_route_uses_problem_details() -> None:
    """Clients receive stable, non-disclosing RFC 9457 errors."""
    client = TestClient(create_app(Settings(app_env="test")))

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "not_found"
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_metrics_route_requires_bearer_secret() -> None:
    """Metrics stay protected even when a local caller reaches the route."""
    metrics_token = "synthetic-test-token-".ljust(32, "x")
    settings = Settings(app_env="test", metrics_scrape_token=metrics_token)
    client = TestClient(create_app(settings))

    denied = client.get("/metrics")
    allowed = client.get("/metrics", headers={"Authorization": f"Bearer {metrics_token}"})

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert "rag_http_requests_total" in allowed.text


def test_metrics_token_must_be_strong() -> None:
    """Reject weak scrape credentials during settings validation."""
    with pytest.raises(ValidationError):
        Settings(metrics_scrape_token="test-only")  # noqa: S106 - intentionally invalid test input


def test_metrics_route_is_disabled_when_token_is_empty() -> None:
    """An empty local env value must not expose metrics or prevent startup."""
    client = TestClient(create_app(Settings(app_env="test", metrics_scrape_token="")))

    test_token = "synthetic-disabled-metrics-token-123456"
    response = client.get("/metrics", headers={"Authorization": f"Bearer {test_token}"})

    assert response.status_code == 403
