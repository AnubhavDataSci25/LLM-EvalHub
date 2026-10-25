"""Dataset domain: Dataset -> DatasetVersion -> TestCase, plus RAG documents."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin


class Dataset(IDMixin, TimestampMixin, Base):
    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(80), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual|csv|json|benchmark
    benchmark_pack_key: Mapped[str | None] = mapped_column(String(80), index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)

    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetVersion.version"
    )

    @property
    def active_version(self) -> DatasetVersion | None:
        for version in self.versions:
            if version.version == self.current_version:
                return version
        return self.versions[-1] if self.versions else None


class DatasetVersion(IDMixin, TimestampMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    test_cases: Mapped[list[TestCase]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class TestCase(IDMixin, TimestampMixin, Base):
    __tablename__ = "test_cases"

    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(80), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ground_truth: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    difficulty: Mapped[str | None] = mapped_column(String(24), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)

    version: Mapped[DatasetVersion] = relationship(back_populates="test_cases")


class Document(IDMixin, TimestampMixin, Base):
    """A source document ingested for RAG evaluation."""

    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="text/plain")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    collection: Mapped[str] = mapped_column(String(80), default="default", index=True)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(IDMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collection: Mapped[str] = mapped_column(String(80), default="default", index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="chunks")
