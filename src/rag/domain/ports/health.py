"""Service health probe port used by operational API endpoints."""

from typing import Protocol


class DependencyProbe(Protocol):
    """Bounded connectivity check for a required backing service."""

    async def ping(self) -> bool: ...
