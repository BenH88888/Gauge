"""Unit tests for the PDF extractor."""

from __future__ import annotations

import pytest

from health_app.docchat.extractor import extract_pages

pytestmark = pytest.mark.unit


def test_extract_pages_returns_one_entry_per_page(
    sample_plan_pdf_bytes: bytes,
) -> None:
    pages = extract_pages(sample_plan_pdf_bytes)
    assert len(pages) == 3
    assert [p for p, _ in pages] == [1, 2, 3]
    assert "deductible" in pages[0][1].lower()
    assert "coinsurance" in pages[1][1].lower()
    assert "prescription" in pages[2][1].lower()


def test_extract_pages_rejects_non_pdf_bytes() -> None:
    with pytest.raises(ValueError, match="Not a parseable PDF"):
        extract_pages(b"this is not a pdf")
