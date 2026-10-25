"""Vector store.

Uses FAISS when `faiss-cpu` is installed, otherwise a NumPy brute-force index.
For the dataset sizes this platform targets (hundreds to a few thousand chunks)
brute-force cosine search is exact and fast enough, so FAISS is an optimisation
rather than a requirement — which keeps the install light on low-spec machines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


def faiss_available() -> bool:
    try:  # pragma: no cover - optional
        import faiss  # noqa: F401

        return True
    except Exception:
        return False


@dataclass(slots=True)
class ScoredChunk:
    chunk_id: str
    content: str
    score: float
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "score": round(self.score, 4),
            "metadata": self.metadata,
        }


class VectorIndex:
    """In-memory index over one collection. Rebuilt from the database on demand."""

    def __init__(self, backend: str = "auto") -> None:
        requested = (backend or "auto").lower()
        self.backend = (
            "faiss" if requested in {"auto", "faiss"} and faiss_available() else "numpy"
        )
        if requested == "faiss" and self.backend != "faiss":
            logger.warning("faiss requested but unavailable; falling back to numpy index")
        self._matrix: np.ndarray | None = None
        self._index: Any | None = None
        self._ids: list[str] = []
        self._contents: list[str] = []
        self._metadata: list[dict[str, Any]] = []

    @property
    def size(self) -> int:
        return len(self._ids)

    def build(
        self,
        ids: list[str],
        vectors: np.ndarray,
        contents: list[str],
        metadata: list[dict[str, Any]],
    ) -> None:
        self._ids = list(ids)
        self._contents = list(contents)
        self._metadata = list(metadata)
        if vectors.size == 0:
            self._matrix = None
            self._index = None
            return
        matrix = np.ascontiguousarray(vectors.astype(np.float32))
        self._matrix = matrix
        if self.backend == "faiss":  # pragma: no cover - optional
            import faiss

            index = faiss.IndexFlatIP(matrix.shape[1])  # vectors are L2-normalised
            index.add(matrix)
            self._index = index

    def search(self, query_vector: np.ndarray, top_k: int = 4) -> list[ScoredChunk]:
        if self._matrix is None or not self._ids:
            return []
        top_k = max(1, min(int(top_k), len(self._ids)))
        query = np.ascontiguousarray(query_vector.astype(np.float32).reshape(1, -1))

        if self.backend == "faiss" and self._index is not None:  # pragma: no cover
            scores, indices = self._index.search(query, top_k)
            pairs = list(zip(indices[0].tolist(), scores[0].tolist(), strict=False))
        else:
            sims = (self._matrix @ query[0]).astype(float)
            order = np.argsort(-sims)[:top_k]
            pairs = [(int(i), float(sims[i])) for i in order]

        results: list[ScoredChunk] = []
        for idx, score in pairs:
            if idx < 0 or idx >= len(self._ids):
                continue
            results.append(
                ScoredChunk(
                    chunk_id=self._ids[idx],
                    content=self._contents[idx],
                    score=float(score),
                    metadata=self._metadata[idx],
                )
            )
        return results

    def describe(self) -> dict[str, Any]:
        return {"backend": self.backend, "vectors": self.size}


class VectorStoreCache:
    """Process-local cache of built indexes, keyed by collection + embedder."""

    def __init__(self) -> None:
        self._indexes: dict[str, VectorIndex] = {}

    def key(self, collection: str, embedder: str) -> str:
        return f"{collection}::{embedder}"

    def get(self, collection: str, embedder: str) -> VectorIndex | None:
        return self._indexes.get(self.key(collection, embedder))

    def put(self, collection: str, embedder: str, index: VectorIndex) -> None:
        self._indexes[self.key(collection, embedder)] = index

    def invalidate(self, collection: str | None = None) -> None:
        if collection is None:
            self._indexes.clear()
            return
        for key in [k for k in self._indexes if k.startswith(f"{collection}::")]:
            self._indexes.pop(key, None)


vector_cache = VectorStoreCache()
