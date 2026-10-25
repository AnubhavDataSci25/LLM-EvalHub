"""Chunking built on LangChain's RecursiveCharacterTextSplitter.

Chunk size and overlap are experiment-level configuration, because "increase
chunk overlap" is one of the concrete remediation steps the diagnosis engine can
recommend — and the improvement loop needs to be able to actually apply it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.rag.ingestion import ParsedDocument


@dataclass(slots=True)
class Chunk:
    index: int
    content: str
    metadata: dict[str, Any]


def build_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    chunk_size = max(120, min(4000, int(chunk_size)))
    chunk_overlap = max(0, min(chunk_size // 2, int(chunk_overlap)))
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""],
        length_function=len,
        keep_separator=True,
    )


def chunk_document(
    document: ParsedDocument,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """Split a parsed document, tracking page numbers where available."""
    splitter = build_splitter(
        chunk_size if chunk_size is not None else settings.default_chunk_size,
        chunk_overlap if chunk_overlap is not None else settings.default_chunk_overlap,
    )
    chunks: list[Chunk] = []

    if document.pages and len(document.pages) > 1:
        for page_number, page_text in enumerate(document.pages, start=1):
            if not page_text.strip():
                continue
            for piece in splitter.split_text(page_text):
                if not piece.strip():
                    continue
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        content=piece.strip(),
                        metadata={
                            "source": document.filename,
                            "page": page_number,
                            "citation": f"{document.filename}#page={page_number}",
                        },
                    )
                )
    else:
        for piece in splitter.split_text(document.text):
            if not piece.strip():
                continue
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=piece.strip(),
                    metadata={"source": document.filename, "citation": document.filename},
                )
            )
    return chunks
