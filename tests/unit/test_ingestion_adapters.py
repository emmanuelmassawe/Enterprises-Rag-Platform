"""Contract-focused tests for object storage, queue, parser, and embedding adapters."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from rag.adapters.blob import s3 as s3_module
from rag.adapters.blob.local import LocalBlobStore
from rag.adapters.blob.s3 import S3BlobStore
from rag.adapters.embeddings import gemini as gemini_module
from rag.adapters.embeddings.gemini import EmbeddingProviderUnavailable, GeminiEmbeddings
from rag.adapters.pdf import parser
from rag.adapters.pdf.parser import PdfRejected, parse_pdf
from rag.adapters.redis.ingestion_queue import ArqIngestionQueue


@pytest.mark.asyncio
async def test_local_blob_store_round_trip_and_path_escape(tmp_path: Path) -> None:
    store = LocalBlobStore(str(tmp_path / "objects"))
    await store.put("tenant/doc.pdf", BytesIO(b"private data"))
    output = BytesIO()
    await store.download("tenant/doc.pdf", output)
    assert output.getvalue() == b"private data"
    await store.delete("tenant/doc.pdf")
    assert not (tmp_path / "objects" / "tenant" / "doc.pdf").exists()
    with pytest.raises(ValueError):
        await store.delete("../escape")


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def upload_fileobj(self, source, bucket, key, **kwargs) -> None:
        self.objects[key] = source.read()

    def download_fileobj(self, bucket, key, destination) -> None:
        destination.write(self.objects[key])

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.mark.asyncio
async def test_s3_blob_store_uses_managed_upload_and_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeS3Client()
    monkeypatch.setattr(s3_module.boto3, "client", lambda *args, **kwargs: client)
    store = S3BlobStore(
        bucket="private-test-bucket",
        region="us-east-1",
        endpoint_url=None,
        access_key_id=None,
        secret_access_key=None,
    )
    await store.put("tenant/object.pdf", BytesIO(b"payload"))
    output = BytesIO()
    await store.download("tenant/object.pdf", output)
    assert output.getvalue() == b"payload"
    await store.delete("tenant/object.pdf")
    assert client.deleted == ["tenant/object.pdf"]


@pytest.mark.asyncio
async def test_gemini_embedding_batches_individual_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call: dict[str, object] = {}

    class Models:
        async def embed_content(self, **kwargs):
            call.update(kwargs)
            return SimpleNamespace(
                embeddings=[SimpleNamespace(values=[0.1, 0.2]), SimpleNamespace(values=[0.3, 0.4])]
            )

    class AsyncClient:
        models = Models()

        async def aclose(self) -> None:
            return None

    class Client:
        def __init__(self, **kwargs) -> None:
            self.aio = AsyncClient()

    monkeypatch.setattr(gemini_module.genai, "Client", Client)
    adapter = GeminiEmbeddings("synthetic-key", "gemini-embedding-2", 2, 5)
    vectors = await adapter.embed(["first", "second"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert call["model"] == "gemini-embedding-2"
    assert len(call["contents"]) == 2
    await adapter.close()


@pytest.mark.asyncio
async def test_gemini_embedding_rejects_unbounded_batch_and_wrong_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Models:
        async def embed_content(self, **kwargs):
            return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1])])

    class AsyncClient:
        models = Models()

        async def aclose(self) -> None:
            return None

    class Client:
        def __init__(self, **kwargs) -> None:
            self.aio = AsyncClient()

    monkeypatch.setattr(gemini_module.genai, "Client", Client)
    adapter = GeminiEmbeddings("synthetic-key", "gemini-embedding-2", 2, 5)
    with pytest.raises(ValueError):
        await adapter.embed(["item"] * 101)
    with pytest.raises(EmbeddingProviderUnavailable, match="shape"):
        await adapter.embed(["one", "two"])


@pytest.mark.asyncio
async def test_arq_queue_enqueues_stable_opaque_job_ids() -> None:
    class Pool:
        def __init__(self) -> None:
            self.jobs: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

        async def enqueue_job(self, function, *args, **kwargs):
            self.jobs.append((function, args, kwargs))
            return object()

        async def ping(self) -> bool:
            return True

        async def close(self) -> None:
            return None

    queue = ArqIngestionQueue("redis://localhost:6379/0")
    pool = Pool()
    queue._pool = pool
    tenant, doc, job = uuid4(), uuid4(), uuid4()
    await queue.enqueue(tenant, doc, job)
    await queue.enqueue_delete(tenant, doc, job)
    assert pool.jobs[0][0] == "process_document"
    assert pool.jobs[1][0] == "process_delete"
    assert pool.jobs[0][2]["_job_id"] == f"ingest:{job}"
    assert pool.jobs[0][1] == (str(tenant), str(doc), str(job))
    assert await queue.ping()
    await queue.close()


def test_pdf_parser_rejects_invalid_and_empty_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not a pdf")
    with pytest.raises(PdfRejected, match="pdf_invalid"):
        parse_pdf(invalid, 10)

    class Page:
        def get_contents(self):
            return None

        def extract_text(self):
            return ""

    class Reader:
        is_encrypted = False
        pages = [Page()]

    monkeypatch.setattr(parser, "PdfReader", lambda *args, **kwargs: Reader())
    with pytest.raises(PdfRejected, match="pdf_no_extractable_text"):
        parse_pdf(invalid, 10)


def test_pdf_parser_checks_encryption_pages_and_content_stream_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "valid.pdf"
    path.write_bytes(b"%PDF-1.7")

    class Reader:
        def __init__(self, *, encrypted: bool = False, pages: list[object] | None = None) -> None:
            self.is_encrypted = encrypted
            self.pages = pages or []

    monkeypatch.setattr(parser, "PdfReader", lambda *args, **kwargs: Reader(encrypted=True))
    with pytest.raises(PdfRejected, match="pdf_encrypted"):
        parse_pdf(path, 10)

    monkeypatch.setattr(parser, "PdfReader", lambda *args, **kwargs: Reader(pages=[object()] * 3))
    with pytest.raises(PdfRejected, match="pdf_page_limit"):
        parse_pdf(path, 2)

    class LargeContents:
        def get_data(self):
            return b"x" * (parser.MAX_PAGE_CONTENT_BYTES + 1)

    class Page:
        def get_contents(self):
            return LargeContents()

        def extract_text(self):
            return "text"

    monkeypatch.setattr(parser, "PdfReader", lambda *args, **kwargs: Reader(pages=[Page()]))
    with pytest.raises(PdfRejected, match="pdf_page_content_limit"):
        parse_pdf(path, 2)
