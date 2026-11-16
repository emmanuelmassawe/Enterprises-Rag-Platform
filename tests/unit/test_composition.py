"""Composition-root smoke test for FR-STA-001."""

from rag.composition import app


def test_req_fr_sta_001_composition_registers_liveness_route() -> None:
    """The production composition root must expose the same liveness contract."""
    assert app.title == "enterprise-rag-api"
    assert any(getattr(route, "path", None) == "/healthz" for route in app.routes)
