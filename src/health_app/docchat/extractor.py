"""PDF text extraction with page provenance.

This is the dumb-but-reliable approach: pypdf's per-page text extraction.
Plan documents lean heavily on tables, which pypdf renders as best-effort
text. For richer table fidelity we can swap in pdfplumber later without
touching anything downstream.
"""

from __future__ import annotations

import io

from pypdf import PdfReader


def extract_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Return a list of (page_number, text) tuples, page numbers 1-indexed.

    Args:
        pdf_bytes: The raw PDF file contents.

    Returns:
        One entry per page with the page number and its extracted text.
        Pages with no extractable text return an empty string rather than
        being skipped, so downstream consumers can still report page count.

    Raises:
        ValueError: If the bytes don't parse as a PDF.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise ValueError(f"Not a parseable PDF: {e}") from e

    out: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            # Some PDFs have malformed pages; carry on with an empty page
            # rather than failing the entire upload.
            text = ""
        out.append((i, text))
    return out
