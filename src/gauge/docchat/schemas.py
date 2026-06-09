"""Pydantic schemas for the document chatbot."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Chunk(BaseModel):
    """A retrievable slice of a document with page provenance."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    chunk_index: int
    text: str
    page_numbers: list[int] = Field(description="1-indexed pages this chunk's text spans.")


class DocumentMeta(BaseModel):
    """Metadata returned to clients about an uploaded document."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    filename: str
    n_pages: int
    n_chunks: int
    uploaded_at: datetime


class UploadResponse(BaseModel):
    """POST /documents response."""

    document: DocumentMeta


class Citation(BaseModel):
    """A reference back to the source document used in an answer."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    chunk_index: int
    page_numbers: list[int]
    snippet: str = Field(description="Short excerpt for display.")


class ChatTurn(BaseModel):
    """A single completed exchange in a conversation.

    Used to pass prior turns to the LLM so answers are contextually aware
    of what has already been asked and answered in the session.
    """

    model_config = ConfigDict(frozen=True)

    question: str
    answer: str


class ChatRequest(BaseModel):
    """POST /chat body."""

    document_id: str
    question: str = Field(min_length=1, max_length=2_000)
    history: list[ChatTurn] = Field(
        default_factory=list,
        description="Prior turns in this conversation, oldest first.",
    )
    top_k: int = Field(default=4, ge=1, le=20)


class ChatResponse(BaseModel):
    """POST /chat response."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    question: str
    answer: str
    citations: list[Citation]
    llm_used: str = Field(description="Identifier for the LLM that produced the answer.")
