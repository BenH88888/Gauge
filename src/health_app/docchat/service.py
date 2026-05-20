"""High-level orchestration for upload-then-ask flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from health_app.docchat.chunker import chunk_pages
from health_app.docchat.extractor import extract_pages
from health_app.docchat.llm import EchoLLM, LLMClient
from health_app.docchat.schemas import (
    ChatResponse,
    Citation,
    DocumentMeta,
)
from health_app.docchat.store import InMemoryDocumentStore

CITATION_SNIPPET_LEN = 240


class DocumentChatService:
    """Glue between the store, retrieval index, and LLM client."""

    def __init__(
        self,
        store: InMemoryDocumentStore | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.store = store or InMemoryDocumentStore()
        self.llm = llm or EchoLLM()

    def upload_pdf(self, filename: str, pdf_bytes: bytes) -> DocumentMeta:
        """Extract, chunk, index, and persist a PDF.

        Returns:
            Metadata for the newly stored document.

        Raises:
            ValueError: If the PDF cannot be parsed or contains no text.
        """
        pages = extract_pages(pdf_bytes)
        if not pages:
            raise ValueError("PDF contained zero pages.")

        document_id = uuid.uuid4().hex[:12]
        chunks = chunk_pages(pages, document_id=document_id)
        if not chunks:
            raise ValueError(
                "PDF parsed but produced no extractable text. It may be a "
                "scanned document that needs OCR."
            )

        meta = DocumentMeta(
            document_id=document_id,
            filename=filename,
            n_pages=len(pages),
            n_chunks=len(chunks),
            uploaded_at=datetime.now(timezone.utc),
        )
        self.store.add(meta, chunks)
        return meta

    def ask(
        self, document_id: str, question: str, top_k: int = 4
    ) -> ChatResponse:
        """Answer a question against an uploaded document.

        Raises:
            KeyError: If no document with `document_id` exists.
        """
        stored = self.store.get(document_id)
        if stored is None:
            raise KeyError(document_id)

        results = stored.index.search(question, k=top_k)
        contexts = [chunk for chunk, _ in results]
        answer = self.llm.answer(question, contexts)
        citations = [
            Citation(
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                page_numbers=chunk.page_numbers,
                snippet=_short(chunk.text),
            )
            for chunk in contexts
        ]
        return ChatResponse(
            document_id=document_id,
            question=question,
            answer=answer,
            citations=citations,
            llm_used=self.llm.name,
        )


def _short(text: str) -> str:
    """Single-line preview of a chunk for the UI."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= CITATION_SNIPPET_LEN:
        return cleaned
    return cleaned[: CITATION_SNIPPET_LEN - 1].rstrip() + "..."
