"""Retrievers.

Three strategies, all sharing one interface so an experiment can swap retriever
without touching the evaluation engine:

  * `vector`  — embedding similarity (default),
  * `keyword` — BM25-style lexical scoring, useful as a retrieval baseline,
  * `hybrid`  — reciprocal-rank fusion of the two.

Comparing `vector` against `keyword` on the same dataset is one of the more
informative experiments the platform supports, so keyword retrieval is a real
strategy here rather than a placeholder.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.text import tokenize
from app.models.dataset import DocumentChunk
from app.rag.embeddings import Embedder, get_embedder
from app.rag.vector_store import ScoredChunk, VectorIndex, vector_cache

logger = get_logger(__name__)

RETRIEVER_STRATEGIES = ("vector", "keyword", "hybrid")


@dataclass(slots=True)
class RetrievalResult:
    chunks: list[ScoredChunk]
    strategy: str
    top_k: int
    index_size: int
    embedder: str

    @property
    def contexts(self) -> list[str]:
        return [c.content for c in self.chunks]

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "top_k": self.top_k,
            "index_size": self.index_size,
            "embedder": self.embedder,
            "chunks": [c.as_dict() for c in self.chunks],
        }


def _load_chunks(db: Session, collection: str) -> list[DocumentChunk]:
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.collection == collection)
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    )
    return list(db.execute(stmt).scalars().all())


class KeywordIndex:
    """Compact BM25 implementation over the collection's chunks."""

    def __init__(self, contents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c)) for c in contents]
        self.lengths = [sum(d.values()) or 1 for d in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 1.0
        self.df: Counter[str] = Counter()
        for doc in self.docs:
            self.df.update(doc.keys())
        self.n = len(self.docs) or 1

    def score(self, query: str) -> list[float]:
        terms = tokenize(query)
        scores = [0.0] * len(self.docs)
        for term in terms:
            df = self.df.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for idx, doc in enumerate(self.docs):
                tf = doc.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (
                    1 - self.b + self.b * self.lengths[idx] / self.avg_length
                )
                scores[idx] += idf * (tf * (self.k1 + 1)) / denom
        return scores


class Retriever:
    """Builds (and caches) an index for a collection, then serves queries."""

    def __init__(
        self,
        db: Session,
        collection: str,
        *,
        strategy: str = "vector",
        top_k: int = 4,
        embedder: Embedder | None = None,
        vector_backend: str = "auto",
    ) -> None:
        self.db = db
        self.collection = collection
        self.strategy = strategy if strategy in RETRIEVER_STRATEGIES else "vector"
        self.top_k = max(1, int(top_k))
        self.embedder = embedder or get_embedder()
        self.vector_backend = vector_backend
        self._index: VectorIndex | None = None
        self._keyword: KeywordIndex | None = None
        self._ids: list[str] = []
        self._contents: list[str] = []
        self._metadata: list[dict[str, Any]] = []
        self._ready = False

    async def prepare(self) -> None:
        if self._ready:
            return
        chunks = _load_chunks(self.db, self.collection)
        self._ids = [c.id for c in chunks]
        self._contents = [c.content for c in chunks]
        self._metadata = [dict(c.extra_metadata or {}) for c in chunks]

        if self.strategy in {"keyword", "hybrid"}:
            self._keyword = KeywordIndex(self._contents)

        if self.strategy in {"vector", "hybrid"}:
            cached = vector_cache.get(self.collection, self.embedder.name)
            if cached is not None and cached.size == len(chunks):
                self._index = cached
            else:
                stored = [c.embedding for c in chunks]
                if chunks and all(isinstance(v, list) and v for v in stored):
                    vectors = np.array(stored, dtype=np.float32)
                else:
                    vectors = await self.embedder.embed(self._contents)
                index = VectorIndex(self.vector_backend)
                index.build(self._ids, vectors, self._contents, self._metadata)
                vector_cache.put(self.collection, self.embedder.name, index)
                self._index = index
        self._ready = True

    async def retrieve(self, query: str, top_k: int | None = None) -> RetrievalResult:
        await self.prepare()
        k = max(1, int(top_k or self.top_k))
        size = len(self._ids)
        if size == 0:
            return RetrievalResult([], self.strategy, k, 0, self.embedder.name)

        if self.strategy == "vector":
            query_vec = await self.embedder.embed_one(query)
            chunks = self._index.search(query_vec, k) if self._index else []
        elif self.strategy == "keyword":
            chunks = self._keyword_top(query, k)
        else:
            chunks = await self._hybrid(query, k)

        return RetrievalResult(chunks, self.strategy, k, size, self.embedder.name)

    def _keyword_top(self, query: str, k: int) -> list[ScoredChunk]:
        if self._keyword is None:
            return []
        scores = self._keyword.score(query)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        best = max(scores) if scores else 0.0
        return [
            ScoredChunk(
                chunk_id=self._ids[i],
                content=self._contents[i],
                score=round(scores[i] / best, 4) if best > 0 else 0.0,
                metadata=self._metadata[i],
            )
            for i in order
            if scores[i] > 0
        ]

    async def _hybrid(self, query: str, k: int) -> list[ScoredChunk]:
        """Reciprocal rank fusion — robust to the two scorers' different scales."""
        query_vec = await self.embedder.embed_one(query)
        dense = self._index.search(query_vec, min(k * 3, max(1, len(self._ids)))) if self._index else []
        sparse = self._keyword_top(query, min(k * 3, max(1, len(self._ids))))
        fused: dict[str, float] = {}
        lookup: dict[str, ScoredChunk] = {}
        for rank, chunk in enumerate(dense, start=1):
            fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1 / (60 + rank)
            lookup[chunk.chunk_id] = chunk
        for rank, chunk in enumerate(sparse, start=1):
            fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1 / (60 + rank)
            lookup.setdefault(chunk.chunk_id, chunk)
        ordered = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        best = ordered[0][1] if ordered else 1.0
        results = []
        for chunk_id, score in ordered:
            chunk = lookup[chunk_id]
            results.append(
                ScoredChunk(
                    chunk_id=chunk_id,
                    content=chunk.content,
                    score=round(score / best, 4) if best else 0.0,
                    metadata=chunk.metadata,
                )
            )
        return results
