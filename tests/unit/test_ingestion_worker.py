"""Worker behavior tests with fake provider, storage, and persistence ports."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from arq import Retry

from rag.adapters.embeddings.gemini import EmbeddingProviderUnavailable
from rag.adapters.pdf.parser import PdfRejected
from rag.core.config import Settings
from rag.domain.ports.ingestion import ParsedPage
from rag.workers import ingestion as worker


class FakeRepository:
    def __init__(self, *, job_status: str = "queued") -> None:
        self.job_status = job_status
        self.document = {
            "status": "queued",
            "storage_key": "tenant/document.pdf",
        }
        self.progress: list[tuple[str, int]] = []
        self.finished = None
        self.failure = None
        self.deletion_finished = False
        self.deletion_failed = False

    async def load_for_processing(self, tenant_id, document_id):
        return self.document

    async def get_job(self, tenant_id, job_id):
        return {"status": self.job_status}

    async def set_progress(self, tenant_id, document_id, job_id, status, progress):
        self.progress.append((status, progress))

    async def finish_processing(self, tenant_id, document_id, job_id, chunks, vectors, page_count):
        self.finished = (chunks, vectors, page_count)

    async def fail_processing(self, tenant_id, document_id, job_id, error_code):
        self.failure = error_code

    async def finish_deletion(self, tenant_id, document_id, job_id):
        self.deletion_finished = True

    async def fail_deletion(self, tenant_id, job_id):
        self.deletion_failed = True


class FakeBlobStore:
    def __init__(self, *, fail_delete: bool = False) -> None:
        self.fail_delete = fail_delete
        self.deleted: list[str] = []

    async def download(self, key: str, destination) -> None:
        destination.write(b"%PDF-1.7")

    async def delete(self, key: str) -> None:
        if self.fail_delete:
            raise OSError("storage unavailable")
        self.deleted.append(key)


class FakeEmbeddings:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails

    async def embed(self, contents: list[str]) -> list[list[float]]:
        if self.fails:
            raise EmbeddingProviderUnavailable("provider unavailable")
        return [[0.1, 0.2] for _ in contents]


def _context(repository, blob=None, embeddings=None, *, job_try: int = 1):
    return {
        "repository": repository,
        "blob_store": blob or FakeBlobStore(),
        "embeddings": embeddings or FakeEmbeddings(),
        "job_try": job_try,
    }


@pytest.mark.asyncio
async def test_worker_ingests_text_and_records_page_chunk_and_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker, "get_settings", lambda: Settings(app_env="test"))
    monkeypatch.setattr(
        worker, "parse_pdf", lambda path, max_pages: [ParsedPage(1, "A clear policy paragraph.")]
    )
    repo = FakeRepository()

    await worker.process_document(_context(repo), str(uuid4()), str(uuid4()), str(uuid4()))

    assert repo.finished is not None
    chunks, vectors, count = repo.finished
    assert chunks[0].page == 1 and vectors == [[0.1, 0.2]] and count == 1
    assert repo.progress[0] == ("processing", 5)


@pytest.mark.asyncio
async def test_worker_marks_bad_pdf_as_safe_terminal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "get_settings", lambda: Settings(app_env="test"))

    def reject(path: Path, max_pages: int):
        raise PdfRejected("pdf_invalid")

    monkeypatch.setattr(worker, "parse_pdf", reject)
    repo = FakeRepository()

    await worker.process_document(_context(repo), str(uuid4()), str(uuid4()), str(uuid4()))

    assert repo.failure == "pdf_invalid"


@pytest.mark.asyncio
async def test_worker_retries_embedding_then_marks_final_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker, "get_settings", lambda: Settings(app_env="test"))
    monkeypatch.setattr(
        worker, "parse_pdf", lambda path, max_pages: [ParsedPage(1, "text paragraph")]
    )
    repo = FakeRepository()

    with pytest.raises(Retry):
        await worker.process_document(
            _context(repo, embeddings=FakeEmbeddings(fails=True), job_try=1),
            str(uuid4()),
            str(uuid4()),
            str(uuid4()),
        )
    assert repo.failure is None

    await worker.process_document(
        _context(repo, embeddings=FakeEmbeddings(fails=True), job_try=3),
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
    )
    assert repo.failure == "embedding_provider_unavailable"


@pytest.mark.asyncio
async def test_worker_ignores_cancelled_job_and_completed_delete_is_idempotent() -> None:
    cancelled = FakeRepository(job_status="cancelled")
    await worker.process_document(_context(cancelled), str(uuid4()), str(uuid4()), str(uuid4()))
    assert cancelled.progress == []

    repo, blob = FakeRepository(), FakeBlobStore()
    tenant_id, document_id, job_id = str(uuid4()), str(uuid4()), str(uuid4())
    await worker.process_delete(_context(repo, blob), tenant_id, document_id, job_id)
    assert repo.deletion_finished is True
    assert blob.deleted == ["tenant/document.pdf"]


@pytest.mark.asyncio
async def test_worker_retries_delete_storage_failure_then_reports_retryable_error() -> None:
    repo, blob = FakeRepository(), FakeBlobStore(fail_delete=True)
    args = str(uuid4()), str(uuid4()), str(uuid4())
    with pytest.raises(Retry):
        await worker.process_delete(_context(repo, blob, job_try=1), *args)
    await worker.process_delete(_context(repo, blob, job_try=3), *args)
    assert repo.deletion_failed is True
