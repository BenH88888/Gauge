"""Insurance document chatbot: PDF upload, retrieval, and Q&A.

Public surface kept intentionally small. The orchestrator is
`DocumentChatService`; everything else (extractor, chunker, retrieval
index, LLM client) is composable and pluggable.
"""

from health_app.docchat.chunker import chunk_pages
from health_app.docchat.extractor import extract_pages
from health_app.docchat.index import RetrievalIndex, TfidfRetrievalIndex
from health_app.docchat.llm import EchoLLM, LLMClient, auto_select_llm
from health_app.docchat.schemas import (
    ChatRequest,
    ChatResponse,
    Chunk,
    Citation,
    DocumentMeta,
    UploadResponse,
)
from health_app.docchat.service import DocumentChatService
from health_app.docchat.store import InMemoryDocumentStore

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "Chunk",
    "Citation",
    "DocumentChatService",
    "DocumentMeta",
    "EchoLLM",
    "InMemoryDocumentStore",
    "LLMClient",
    "RetrievalIndex",
    "TfidfRetrievalIndex",
    "UploadResponse",
    "auto_select_llm",
    "chunk_pages",
    "extract_pages",
]
