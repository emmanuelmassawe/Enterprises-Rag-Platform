"""Text extraction with page and decompressed-content limits."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from rag.domain.ports.ingestion import ParsedPage

MAX_PAGE_CONTENT_BYTES = 32 * 1024 * 1024


class PdfRejected(ValueError):
    """PDF cannot be safely parsed within configured limits."""


def parse_pdf(path: Path, max_pages: int) -> list[ParsedPage]:
    """Extract normalized page text; reject encrypted, malformed, and oversized PDFs."""
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise PdfRejected("pdf_encrypted")
        if not 1 <= len(reader.pages) <= max_pages:
            raise PdfRejected("pdf_page_limit")
        pages: list[ParsedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_PAGE_CONTENT_BYTES:
                raise PdfRejected("pdf_page_content_limit")
            pages.append(ParsedPage(index, page.extract_text() or ""))
        if not any(page.text.strip() for page in pages):
            raise PdfRejected("pdf_no_extractable_text")
        return pages
    except PdfRejected:
        raise
    except (PdfReadError, OSError, ValueError, KeyError) as exc:
        raise PdfRejected("pdf_invalid") from exc
