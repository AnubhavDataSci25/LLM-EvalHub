"""Embedding backends.

The platform must run on modest hardware with no local model download, so the
default backend is a deterministic hashed bag-of-n-grams embedder implemented in
pure NumPy. It is honest about what it is — a lexical embedding, not a semantic
one — and the UI labels it as such.

Two upgrades are available without code changes:
  * `gemini`                — hosted embedding API (no local compute),
  * `sentence-transformers` — local semantic embeddings if the optional extra is
                              installed and the machine can afford it.
"""

from __future__ import annotations

import abc
import hashlib
from typing import Any

import httpx
import numpy as np

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.core.text import tokenize

logger = get_logger(__name__)


class Embedder(abc.ABC):
    name: str = "base"
    semantic: bool = False

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> np.ndarray:
        """Return an L2-normalised (n, d) float32 matrix."""

    async def embed_one(self, text: str) -> np.ndarray:
        return (await self.embed([text]))[0]

    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "dimension": self.dimension,
            "semantic": self.semantic,
            "note": (
                "Lexical hashed embedding — fast and dependency-free, but it matches "
                "wording rather than meaning."
                if not self.semantic
                else "Semantic embedding model."
            ),
        }


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class HashingEmbedder(Embedder):
    """Deterministic hashed bag-of-words + bigrams with sublinear term weighting."""

    name = "hashing"
    semantic = False

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimension, dtype=np.float32)
        # Same tokenisation as the evaluators: stemmed, stopwords removed.
        tokens = tokenize(text)
        if not tokens:
            return vec
        grams = list(tokens)
        grams += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        # sublinear scaling keeps very frequent terms from dominating
        return np.sign(vec) * np.log1p(np.abs(vec))

    async def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.vstack([self._vector(t) for t in texts]) if texts else np.zeros(
            (0, self.dimension), dtype=np.float32
        )
        return _normalise(matrix)


class GeminiEmbedder(Embedder):
    """Hosted embeddings via the Gemini `embedContent` endpoint."""

    name = "gemini"
    semantic = True

    def __init__(self, dimension: int, model: str | None = None) -> None:
        super().__init__(dimension)
        self.model = model or settings.embedding_model
        self.api_key = settings.gemini_api_key
        self.base_url = settings.gemini_base_url

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not self.api_key:
            raise ProviderError(
                "Gemini embeddings need GEMINI_API_KEY.",
                provider="gemini",
                kind="provider_not_configured",
            )
        vectors: list[list[float]] = []
        url = f"{self.base_url}/models/{self.model}:batchEmbedContents"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        async with httpx.AsyncClient(timeout=60.0) as client:
            for start in range(0, len(texts), 64):
                batch = texts[start : start + 64]
                payload = {
                    "requests": [
                        {
                            "model": f"models/{self.model}",
                            "content": {"parts": [{"text": t[:9000]}]},
                        }
                        for t in batch
                    ]
                }
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPError as exc:
                    raise ProviderError(
                        f"Gemini embedding request failed: {exc}",
                        provider="gemini",
                        kind="upstream_error",
                        retryable=True,
                    ) from exc
                for item in data.get("embeddings", []):
                    vectors.append(item.get("values", []))
        if not vectors:
            return np.zeros((0, self.dimension), dtype=np.float32)
        matrix = np.array(vectors, dtype=np.float32)
        self.dimension = matrix.shape[1]
        return _normalise(matrix)


class SentenceTransformerEmbedder(Embedder):  # pragma: no cover - optional extra
    name = "sentence-transformers"
    semantic = True

    def __init__(self, dimension: int, model: str | None = None) -> None:
        super().__init__(dimension)
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model or "sentence-transformers/all-MiniLM-L6-v2")
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        matrix = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return _normalise(np.asarray(matrix, dtype=np.float32))


def get_embedder(backend: str | None = None, model: str | None = None) -> Embedder:
    """Build the configured embedder, degrading to hashing with a clear log line."""
    backend = (backend or settings.embedding_backend or "hashing").lower()
    dimension = settings.embedding_dimension
    if backend == "gemini":
        if settings.gemini_api_key:
            return GeminiEmbedder(dimension, model)
        logger.warning("gemini embeddings requested without an API key; using hashing backend")
        return HashingEmbedder(dimension)
    if backend in {"sentence-transformers", "st", "local"}:
        try:
            return SentenceTransformerEmbedder(dimension, model)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "sentence-transformers unavailable (%s); using hashing backend", exc
            )
            return HashingEmbedder(dimension)
    return HashingEmbedder(dimension)
