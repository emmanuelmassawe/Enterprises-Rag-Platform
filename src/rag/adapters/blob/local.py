"""Atomic local-disk BlobStore for isolated development and tests."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO


class LocalBlobStore:
    """Store opaque object keys beneath a fixed root using atomic file replacement."""

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("invalid object key")
        return candidate

    async def put(self, key: str, source: BinaryIO) -> None:
        await asyncio.to_thread(self._put, key, source)

    def _put(self, key: str, source: BinaryIO) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.seek(0)
        descriptor, temporary = tempfile.mkstemp(dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def download(self, key: str, destination: BinaryIO) -> None:
        await asyncio.to_thread(self._download, key, destination)

    def _download(self, key: str, destination: BinaryIO) -> None:
        with self._path(key).open("rb") as source:
            shutil.copyfileobj(source, destination, length=1024 * 1024)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete, key)

    def _delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
