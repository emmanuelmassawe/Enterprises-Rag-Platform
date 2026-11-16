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


def test_readyz_reports_missing_dependencies_as_not_ready() -> None:
    """Readiness requires the database and shared rate limiter after milestone two."""
    client = TestClient(create_app(Settings(app_env="test")))

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "api": "ok",
            "database": "not_configured",
            "rate_limiter": "local_fallback",
            "ingestion_queue": "not_configured",
        },
    }


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
    settings = Settings(app_env="test", metrics_scrape_token="a" * 32)
    client = TestClient(create_app(settings))

    denied = client.get("/metrics")
    allowed = client.get("/metrics", headers={"Authorization": f"Bearer {'a' * 32}"})

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert "rag_http_requests_total" in allowed.text


def test_metrics_token_must_be_strong() -> None:
    """Reject weak scrape credentials during settings validation."""
    with pytest.raises(ValidationError):
        Settings(metrics_scrape_token="short")  # noqa: S106 - intentionally weak validation input


def test_metrics_route_is_disabled_when_token_is_empty() -> None:
    """An empty local env value must not expose metrics or prevent startup."""
    client = TestClient(create_app(Settings(app_env="test", metrics_scrape_token="")))

    response = client.get("/metrics", headers={"Authorization": f"Bearer {'a' * 40}"})

    assert response.status_code == 403
