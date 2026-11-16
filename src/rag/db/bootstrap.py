"""Create the first tenant and one-time admin API key using migration credentials."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from rag.adapters.postgres.models import ApiKey, Tenant
from rag.core.config import get_settings


async def _bootstrap(tenant_name: str) -> None:
    settings = get_settings()
    if settings.migration_database_url is None:
        raise RuntimeError("MIGRATION_DATABASE_URL is required for first-tenant bootstrap")
    tenant_id, key_id = uuid4(), uuid4()
    secret = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    engine = create_async_engine(
        settings.migration_database_url.get_secret_value(),
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        connect_args={"timeout": 3, "command_timeout": 10},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Tenant).values(id=tenant_id, name=tenant_name.strip(), created_at=now)
            )
            await connection.execute(
                insert(ApiKey).values(
                    id=key_id,
                    tenant_id=tenant_id,
                    name="bootstrap admin",
                    secret_hash=hashlib.sha256(secret.encode("ascii")).hexdigest(),
                    scopes=["admin"],
                    created_at=now,
                )
            )
    finally:
        await engine.dispose()
    # This is the sole issuance channel; stdout is intentionally one-time secret output.
    sys.stdout.write(
        json.dumps(
            {
                "tenant_id": str(tenant_id),
                "api_key_id": str(key_id),
                "api_key": f"rag.{tenant_id}.{key_id}.{secret}",
            }
        )
        + "\n"
    )


def main() -> None:
    """Validate one tenant label and issue its initial admin credential once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-name", required=True, help="Human-readable tenant label")
    args = parser.parse_args()
    tenant_name = args.tenant_name.strip()
    if not tenant_name or len(tenant_name) > 160:
        parser.error("--tenant-name must contain between 1 and 160 characters")
    asyncio.run(_bootstrap(tenant_name))


if __name__ == "__main__":
    main()
