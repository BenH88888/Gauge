"""Retrieval index over chunks.

The default implementation uses TF-IDF (via scikit-learn), which is
already a project dependency and gives surprisingly strong retrieval on
short, domain-specific corpora like a single plan document. Dense
embedding alternatives (sentence-transformers, OpenAI embeddings, etc.)
can be slotted in later behind the same protocol without changing any
callers.
"""

from __future__ import annotations

from typing import Protocol

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from health_app.docchat.schemas import Chunk


class RetrievalIndex(Protocol):
    """Protocol every chunk index conforms to."""

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        """Return the top-k (chunk, score) pairs ranked by relevance."""
        ...


class TfidfRetrievalIndex:
    """TF-IDF + cosine similarity retrieval over a single document.

    A new instance is built per document so the vocabulary stays tight
    and document-specific. That's a reasonable choice for plan documents
    where each PDF is its own self-contained corpus.
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        if not chunks:
            raise ValueError(
                "TfidfRetrievalIndex requires at least one chunk."
            )
        self._chunks = list(chunks)
        texts = [c.text for c in self._chunks]
        try:
            self._vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words="english",
                ngram_range=(1, 2),
                min_df=1,
            )
            self._matrix = self._vectorizer.fit_transform(texts)
        except ValueError:
            # All tokens were stop words; rebuild without the filter so
            # we still produce some retrieval signal.
            self._vectorizer = TfidfVectorizer(
                lowercase=True,
                ngram_range=(1, 2),
                min_df=1,
            )
            self._matrix = self._vectorizer.fit_transform(texts)

    @property
    def size(self) -> int:
        return len(self._chunks)

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        if not query.strip():
            return []
        query_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self._matrix).ravel()
        # Pick the top-k by score; argsort returns ascending so we slice from end.
        top = sims.argsort()[::-1][: max(1, k)]
        return [
            (self._chunks[int(i)], float(sims[int(i)]))
            for i in top
            if sims[int(i)] > 0.0
        ]
