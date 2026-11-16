"""Document-ingestion rules independent of HTTP, SQLAlchemy, and provider SDKs."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from typing import BinaryIO
from uuid import UUID, uuid4

from rag.domain.ports.ingestion import (
    BlobStore,
    IngestionApplication,
    IngestionChunk,
    IngestionRepository,
    InjectionDetector,
    ParsedPage,
    QueueBackend,
    QueueCapacityExceeded,
    QueueUnavailable,
    StorageUnavailable,
    UploadRejected,
)

INJECTION_PATTERNS = (
    re.compile(
        r"\b(ignore|disregard|override) (all |any )?(previous|prior|above) instructions\b", re.I
    ),
    re.compile(r"\b(system prompt|developer message|secret key|api key)\b", re.I),
    re.compile(r"\b(reveal|exfiltrate|print|show) (the )?(hidden|system|secret)\b", re.I),
)


def normalize_extracted_text(value: str) -> str:
    """Normalize PDF text and remove control characters used for hidden instructions."""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        character
        for character in normalized
        if character in "\n\t" or unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
    )


class HeuristicInjectionDetector:
    """Conservative instruction-pattern detector; suspicious content stays quarantined."""

    def is_suspicious(self, content: str) -> bool:
        return any(pattern.search(content) for pattern in INJECTION_PATTERNS)


def chunk_pages(
    pages: Sequence[ParsedPage],
    *,
    max_chars: int,
    overlap_chars: int,
    detector: InjectionDetector | None = None,
) -> list[IngestionChunk]:
    """Split text deterministically while preserving page provenance and bounded overlap."""
    if max_chars < 1 or not 0 <= overlap_chars < max_chars:
        raise ValueError("chunk size must be positive and overlap smaller than chunk size")
    chunks: list[IngestionChunk] = []
    scanner = detector or HeuristicInjectionDetector()
    for page in pages:
        text = normalize_extracted_text(page.text)
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        current = ""
        for paragraph in paragraphs:
            while len(paragraph) > max_chars:
                if current:
                    chunks.append(_chunk(len(chunks), current, page.page, scanner))
                    current = current[-overlap_chars:] if overlap_chars else ""
                cut = paragraph.rfind(" ", 0, max_chars + 1)
                cut = max_chars if cut < max_chars // 2 else cut
                chunks.append(_chunk(len(chunks), paragraph[:cut].strip(), page.page, scanner))
                paragraph = paragraph[max(0, cut - overlap_chars) :].strip()
            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if len(candidate) <= max_chars:
                current = candidate
            else:
                chunks.append(_chunk(len(chunks), current, page.page, scanner))
                current = (current[-overlap_chars:] + "\n\n" if overlap_chars else "") + paragraph
        if current:
            chunks.append(_chunk(len(chunks), current, page.page, scanner))
    return chunks


def _chunk(ordinal: int, content: str, page: int, detector: InjectionDetector) -> IngestionChunk:
    return IngestionChunk(
        ordinal=ordinal,
        content=content,
        page=page,
        section=None,
        quarantined=detector.is_suspicious(content),
    )


class IngestionService(IngestionApplication):
    """Coordinate a streamed upload, tenant persistence, and deterministic queue job."""

    def __init__(
        self,
        repository: IngestionRepository,
        blob_store: BlobStore,
        queue: QueueBackend,
        *,
        max_upload_bytes: int,
        max_queue_size: int,
    ) -> None:
        self.repository = repository
        self.blob_store = blob_store
        self.queue = queue
        self.max_upload_bytes = max_upload_bytes
        self.max_queue_size = max_queue_size

    async def accept_upload(
        self,
        *,
        tenant_id: UUID,
        collection_id: UUID,
        filename: str,
        content_type: str | None,
        size_bytes: int,
        content_hash: str,
        idempotency_key: str,
        metadata: dict[str, str | int | float | bool | None],
        storage_key: str,
        source: BinaryIO,
    ) -> tuple[UUID, UUID, bool]:
        if size_bytes < 1 or size_bytes > self.max_upload_bytes:
            raise UploadRejected("upload_size_invalid")
        if not filename.lower().endswith(".pdf") or content_type != "application/pdf":
            raise UploadRejected("unsupported_media_type")
        idem_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        request_digest = hashlib.sha256(
            json.dumps(
                [collection_id.hex, content_hash, metadata], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        document_id, job_id = uuid4(), uuid4()
        try:
            try:
                await self.blob_store.put(storage_key, source)
            except Exception as exc:
                raise StorageUnavailable("blob store unavailable") from exc
            result = await self.repository.create_upload(
                tenant_id,
                collection_id,
                document_id,
                job_id,
                content_hash,
                filename,
                size_bytes,
                metadata,
                storage_key,
                idem_hash,
                request_digest,
                self.max_queue_size,
            )
            if result.created:
                try:
                    await self.queue.enqueue(tenant_id, result.document_id, result.job_id)
                except Exception as exc:
                    await self.repository.delete_upload(tenant_id, result.document_id, idem_hash)
                    await self.blob_store.delete(storage_key)
                    raise QueueUnavailable("queue_unavailable") from exc
            else:
                await self.blob_store.delete(storage_key)
        except QueueCapacityExceeded as exc:
            await self.blob_store.delete(storage_key)
            raise QueueUnavailable("queue_full") from exc
        except StorageUnavailable:
            raise
        except Exception:
            await self.blob_store.delete(storage_key)
            raise
        return result.document_id, result.job_id, result.created
