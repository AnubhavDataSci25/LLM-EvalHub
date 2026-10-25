"""Document ingestion + indexing service for RAG evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.db.base import new_id
from app.models.dataset import Document, DocumentChunk
from app.rag.chunking import chunk_document
from app.rag.embeddings import get_embedder
from app.rag.ingestion import parse_document, safe_filename, validate_upload
from app.rag.retriever import Retriever
from app.rag.vector_store import vector_cache

logger = get_logger(__name__)


class RagService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- documents ---------------------------------------------------------
    def get(self, document_id: str) -> Document:
        document = self.db.get(Document, document_id)
        if document is None:
            raise NotFoundError(f"Document '{document_id}' was not found.")
        return document

    def list(self, *, collection: str | None = None, limit: int = 100) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc()).limit(limit)
        if collection:
            stmt = stmt.where(Document.collection == collection)
        return list(self.db.execute(stmt).scalars().all())

    def collections(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(
                Document.collection,
                func.count(Document.id),
                func.coalesce(func.sum(Document.chunk_count), 0),
            ).group_by(Document.collection)
        ).all()
        return [
            {
                "name": name,
                "documents": int(doc_count),
                "chunks": int(chunk_count),
                "indexed": int(chunk_count) > 0,
            }
            for name, doc_count, chunk_count in rows
        ]

    def store_upload(
        self, *, filename: str, content: bytes, content_type: str | None, collection: str
    ) -> Document:
        validate_upload(filename, content_type, len(content))
        clean_name = safe_filename(filename)
        settings.ensure_dirs()
        document = Document(
            id=new_id("doc"),
            filename=clean_name,
            content_type=content_type or "application/octet-stream",
            byte_size=len(content),
            collection=collection or "default",
            status="uploaded",
        )
        target = settings.uploads_dir / f"{document.id}{Path(clean_name).suffix.lower()}"
        target.write_bytes(content)
        document.config = {"path": str(target)}
        self.db.add(document)
        self.db.flush()
        logger.info("stored upload %s (%s bytes)", document.id, len(content))
        return document

    def register_local_file(self, path: Path, *, collection: str) -> Document:
        """Register a file already on disk (used when installing benchmark packs)."""
        content = path.read_bytes()
        return self.store_upload(
            filename=path.name,
            content=content,
            content_type="text/markdown" if path.suffix in {".md", ".markdown"} else "text/plain",
            collection=collection,
        )

    # -- indexing ----------------------------------------------------------
    async def index(
        self,
        document_ids: list[str],
        *,
        collection: str = "default",
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        embedding_backend: str | None = None,
    ) -> dict[str, Any]:
        if not document_ids:
            document_ids = [d.id for d in self.list(collection=collection)]
        if not document_ids:
            raise ValidationFailedError("No documents to index. Upload a document first.")

        embedder = get_embedder(embedding_backend)
        indexed, failed, total_chunks = [], [], 0

        for document_id in document_ids:
            document = self.get(document_id)
            path = Path((document.config or {}).get("path", ""))
            if not path.exists():
                document.status = "failed"
                document.error = "The stored file is missing from disk."
                failed.append({"document_id": document_id, "error": document.error})
                continue
            try:
                parsed = parse_document(path, filename=document.filename)
                chunks = chunk_document(
                    parsed, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
                if not chunks:
                    raise ValidationFailedError("Document produced no chunks.")
                vectors = await embedder.embed([c.content for c in chunks])

                # replace any previous chunks for this document
                for existing in list(document.chunks):
                    self.db.delete(existing)
                self.db.flush()

                for chunk, vector in zip(chunks, vectors, strict=False):
                    self.db.add(
                        DocumentChunk(
                            id=new_id("chk"),
                            document_id=document.id,
                            collection=collection,
                            chunk_index=chunk.index,
                            content=chunk.content,
                            embedding=[round(float(v), 6) for v in vector.tolist()],
                            extra_metadata=chunk.metadata,
                        )
                    )
                document.collection = collection
                document.chunk_count = len(chunks)
                document.status = "indexed"
                document.error = None
                document.config = {
                    **(document.config or {}),
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "embedding": embedder.describe(),
                    "pages": parsed.page_count,
                }
                total_chunks += len(chunks)
                indexed.append(document.id)
            except Exception as exc:
                logger.warning("indexing failed for %s: %s", document_id, exc)
                document.status = "failed"
                document.error = str(exc)[:500]
                failed.append({"document_id": document_id, "error": document.error})

        self.db.flush()
        vector_cache.invalidate(collection)
        return {
            "collection": collection,
            "indexed": indexed,
            "failed": failed,
            "chunks": total_chunks,
            "embedding": embedder.describe(),
        }

    def delete(self, document_id: str) -> None:
        document = self.get(document_id)
        collection = document.collection
        path = Path((document.config or {}).get("path", ""))
        self.db.delete(document)
        self.db.flush()
        vector_cache.invalidate(collection)
        if path.exists():
            try:
                path.unlink()
            except OSError:  # pragma: no cover
                logger.warning("could not remove file %s", path)

    # -- retrieval preview --------------------------------------------------
    async def preview(
        self, *, query: str, collection: str, top_k: int, strategy: str
    ) -> dict[str, Any]:
        retriever = Retriever(
            self.db,
            collection,
            strategy=strategy,
            top_k=top_k,
            embedder=get_embedder(),
            vector_backend=settings.vector_store_backend,
        )
        result = await retriever.retrieve(query, top_k)
        payload = result.as_dict()
        payload["query"] = query
        if not payload["chunks"]:
            payload["note"] = (
                "Nothing was retrieved. Check that documents in this collection have been indexed."
            )
        return payload
