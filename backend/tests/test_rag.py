"""RAG pipeline: ingestion, chunking, embedding, retrieval."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationFailedError
from app.rag.chunking import chunk_document
from app.rag.embeddings import HashingEmbedder, get_embedder
from app.rag.ingestion import ParsedDocument, parse_document, safe_filename, validate_upload
from app.rag.retriever import KeywordIndex
from app.rag.vector_store import VectorIndex

HANDBOOK = """
Refunds are available within 30 days of purchase for unopened items.

The default rate limit is 120 requests per minute on the Starter plan.

Backups are taken every 6 hours and stored in a separate region.
"""


def test_upload_validation_rejects_bad_types():
    with pytest.raises(ValidationFailedError):
        validate_upload("payload.exe", "application/octet-stream", 100)
    with pytest.raises(ValidationFailedError):
        validate_upload("empty.txt", "text/plain", 0)
    assert validate_upload("notes.md", "text/markdown", 500) == ".md"


def test_upload_size_limit_enforced():
    from app.core.config import settings

    with pytest.raises(ValidationFailedError):
        validate_upload("big.txt", "text/plain", settings.max_upload_bytes + 1)


def test_safe_filename_strips_paths():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert "/" not in safe_filename("a/b/c.md")


def test_markdown_parsing_strips_syntax(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Title\n\nSome **bold** text and a [link](http://x).\n")
    parsed = parse_document(path)
    assert "Title" in parsed.text
    assert "**" not in parsed.text and "http://x" not in parsed.text
    assert "link" in parsed.text


def test_empty_file_rejected(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n  ")
    with pytest.raises(ValidationFailedError):
        parse_document(path)


def test_chunking_respects_size_and_overlap():
    document = ParsedDocument(filename="d.md", text="Sentence number one. " * 200)
    chunks = chunk_document(document, chunk_size=300, chunk_overlap=60)
    assert len(chunks) > 3
    assert all(len(c.content) <= 400 for c in chunks)
    assert chunks[0].metadata["source"] == "d.md"


def test_page_citations_are_tracked():
    document = ParsedDocument(
        filename="report.pdf", text="a\n\nb", page_count=2, pages=["Page one text.", "Page two text."]
    )
    chunks = chunk_document(document, chunk_size=200, chunk_overlap=0)
    assert {c.metadata["page"] for c in chunks} == {1, 2}
    assert chunks[0].metadata["citation"] == "report.pdf#page=1"


@pytest.mark.asyncio
async def test_hashing_embeddings_are_deterministic_and_normalised():
    embedder = HashingEmbedder(256)
    first = await embedder.embed(["refund policy", "rate limits"])
    second = await embedder.embed(["refund policy", "rate limits"])
    assert (first == second).all()
    norms = (first**2).sum(axis=1) ** 0.5
    assert all(abs(n - 1.0) < 1e-5 for n in norms)


@pytest.mark.asyncio
async def test_embedder_falls_back_without_credentials():
    embedder = get_embedder("gemini")  # no GEMINI_API_KEY in the test env
    assert embedder.name == "hashing"
    assert embedder.semantic is False


@pytest.mark.asyncio
async def test_vector_search_returns_the_relevant_chunk():
    sentences = [s.strip() for s in HANDBOOK.strip().split("\n\n")]
    embedder = HashingEmbedder(512)
    vectors = await embedder.embed(sentences)
    index = VectorIndex("numpy")
    index.build([f"c{i}" for i in range(len(sentences))], vectors, sentences, [{} for _ in sentences])

    query = await embedder.embed_one("What is the refund window?")
    top = index.search(query, top_k=1)
    assert top and "30 days" in top[0].content


def test_keyword_bm25_ranks_the_matching_passage_first():
    sentences = [s.strip() for s in HANDBOOK.strip().split("\n\n")]
    index = KeywordIndex(sentences)
    scores = index.score("rate limit requests per minute")
    assert scores.index(max(scores)) == 1


def test_empty_index_returns_no_results():
    index = VectorIndex("numpy")
    import numpy as np

    index.build([], np.zeros((0, 4), dtype="float32"), [], [])
    assert index.search(np.zeros(4, dtype="float32"), top_k=3) == []
