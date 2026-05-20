"""Unit tests for the EchoLLM fallback."""

from __future__ import annotations

import pytest

from health_app.docchat.llm import EchoLLM
from health_app.docchat.schemas import Chunk

pytestmark = pytest.mark.unit


def test_echo_handles_empty_context() -> None:
    answer = EchoLLM().answer("anything", [])
    assert "couldn't find anything" in answer.lower()


def test_echo_includes_page_citations_and_snippets() -> None:
    chunks = [
        Chunk(
            document_id="d",
            chunk_index=0,
            text="Annual deductible is $1,000 individual.",
            page_numbers=[1],
        ),
        Chunk(
            document_id="d",
            chunk_index=1,
            text="Specialist copay is $50.",
            page_numbers=[2, 3],
        ),
    ]
    answer = EchoLLM().answer("what is the deductible?", chunks)
    assert "$1,000" in answer
    assert "p. 1" in answer
    assert "p. 2, 3" in answer
    assert "ANTHROPIC_API_KEY" in answer
