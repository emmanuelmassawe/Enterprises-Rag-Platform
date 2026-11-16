"""Bootstrap safety checks before any privileged database connection is made."""

from __future__ import annotations

import pytest

from rag.core.config import Settings
from rag.db import bootstrap


@pytest.mark.asyncio
async def test_req_fr_auth_001_bootstrap_requires_separate_migration_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setattr(bootstrap, "get_settings", lambda: Settings(app_env="test"))

    with pytest.raises(RuntimeError, match="MIGRATION_DATABASE_URL"):
        await bootstrap._bootstrap("synthetic tenant")
