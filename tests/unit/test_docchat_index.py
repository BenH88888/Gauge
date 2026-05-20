"""Unit tests for the TF-IDF retrieval index."""

from __future__ import annotations

import pytest

from health_app.docchat.index import TfidfRetrievalIndex
from health_app.docchat.schemas import Chunk

pytestmark = pytest.mark.unit


def _chunk(i: int, text: str, pages: list[int]) -> Chunk:
    return Chunk(
        document_id="d", chunk_index=i, text=text, page_numbers=pages
    )


def test_index_requires_non_empty_chunks() -> None:
    with pytest.raises(ValueError):
        TfidfRetrievalIndex([])


def test_index_returns_topk_in_relevance_order() -> None:
    chunks = [
        _chunk(0, "Annual deductible is one thousand dollars individual.", [1]),
        _chunk(1, "Office visit copay is twenty five dollars.", [2]),
        _chunk(2, "Generic drug copay is ten dollars per prescription.", [3]),
    ]
    index = TfidfRetrievalIndex(chunks)
    results = index.search("how much is the deductible", k=2)
    assert len(results) >= 1
    top_chunk, top_score = results[0]
    assert top_chunk.chunk_index == 0
    assert top_score > 0.0


def test_index_returns_empty_for_blank_query() -> None:
    # Use a non-stop-word so the TF-IDF vocabulary isn't empty.
    chunks = [_chunk(0, "deductible details apply to all members", [1])]
    index = TfidfRetrievalIndex(chunks)
    assert index.search("   ") == []


def test_index_filters_zero_similarity() -> None:
    chunks = [
        _chunk(0, "deductible details", [1]),
        _chunk(1, "specialty drugs coinsurance", [2]),
    ]
    index = TfidfRetrievalIndex(chunks)
    results = index.search("xyzzy unrelated query", k=5)
    # All scores should be zero (no overlap), so search returns nothing.
    assert results == []
