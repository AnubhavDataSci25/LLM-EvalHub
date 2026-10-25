"""Dataset request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DIFFICULTIES = ("easy", "medium", "hard", "adversarial")


class TestCaseBase(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    ground_truth: str | None = Field(default=None, max_length=20000)
    context: str | None = Field(default=None, max_length=60000)
    category: str | None = Field(default=None, max_length=80)
    difficulty: str | None = Field(default=None, max_length=24)
    tags: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("difficulty")
    @classmethod
    def _check_difficulty(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalised = value.strip().lower()
        if normalised not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
        return normalised

    @field_validator("question", "ground_truth", "context")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class TestCaseCreate(TestCaseBase):
    id: str | None = Field(default=None, max_length=80, description="Optional external id")


class TestCaseUpdate(BaseModel):
    question: str | None = None
    ground_truth: str | None = None
    context: str | None = None
    category: str | None = None
    difficulty: str | None = None
    tags: list[str] | None = None
    expected_sources: list[str] | None = None
    metadata: dict[str, Any] | None = None


class TestCaseRead(TestCaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str | None = None
    position: int = 0


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    domain: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list)
    test_cases: list[TestCaseCreate] = Field(default_factory=list)


class DatasetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    domain: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = None


class ValidationIssue(BaseModel):
    row: int | None = None
    field: str | None = None
    severity: Literal["error", "warning"] = "error"
    message: str


class DatasetValidationReport(BaseModel):
    valid: bool
    total_rows: int
    accepted_rows: int
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    detected_columns: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class DatasetVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    notes: str | None = None
    row_count: int
    created_at: datetime
    validation_report: dict[str, Any] = Field(default_factory=dict)


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    domain: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str
    benchmark_pack_key: str | None = None
    current_version: int
    created_at: datetime
    updated_at: datetime
    row_count: int = 0
    version_count: int = 1
    categories: list[str] = Field(default_factory=list)
    difficulties: dict[str, int] = Field(default_factory=dict)
    has_context: bool = False
    has_ground_truth: bool = False


class DatasetDetail(DatasetRead):
    versions: list[DatasetVersionRead] = Field(default_factory=list)
    test_cases: list[TestCaseRead] = Field(default_factory=list)
    validation_report: DatasetValidationReport | None = None


class DatasetImportRequest(BaseModel):
    """JSON import payload (CSV arrives as multipart upload)."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    domain: str | None = None
    tags: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]]


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    byte_size: int
    collection: str
    status: str
    chunk_count: int
    error: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DocumentIndexRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    collection: str = "default"
    chunk_size: int = Field(default=800, ge=120, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    embedding_backend: str | None = None


class RetrievalPreviewRequest(BaseModel):
    query: str = Field(min_length=1)
    collection: str = "default"
    top_k: int = Field(default=4, ge=1, le=20)
    strategy: Literal["vector", "keyword", "hybrid"] = "vector"
