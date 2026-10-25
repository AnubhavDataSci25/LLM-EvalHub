"""Experiment / evaluation domain.

Experiment
  ├── ExperimentModel (one row per provider+model under test)
  └── EvaluationRun (one execution of the experiment)
        └── EvaluationResult (one test case x one model)
              ├── MetricResult
              └── Failure
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin


class PromptTemplate(IDMixin, TimestampMixin, Base):
    """Named prompt with immutable versions, so experiments stay reproducible."""

    __tablename__ = "prompts"

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list[PromptVersion]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan", order_by="PromptVersion.version"
    )


class PromptVersion(IDMixin, TimestampMixin, Base):
    __tablename__ = "prompt_versions"

    prompt_id: Mapped[str] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    template: Mapped[str] = mapped_column(Text, nullable=False)

    prompt: Mapped[PromptTemplate] = relationship(back_populates="versions")


class Experiment(IDMixin, TimestampMixin, Base):
    """A reproducible evaluation configuration."""

    __tablename__ = "experiments"

    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prompt_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL"), index=True
    )
    parent_experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), index=True
    )
    origin: Mapped[str] = mapped_column(String(32), default="manual")  # manual|benchmark|improvement
    benchmark_pack_key: Mapped[str | None] = mapped_column(String(80), index=True)

    # Generation configuration
    system_prompt: Mapped[str | None] = mapped_column(Text)
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    prompt_label: Mapped[str] = mapped_column(String(40), default="v1")
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    max_tokens: Mapped[int] = mapped_column(Integer, default=512)

    # RAG configuration
    rag_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rag_collection: Mapped[str | None] = mapped_column(String(80))
    retriever: Mapped[str] = mapped_column(String(40), default="vector")
    chunk_size: Mapped[int] = mapped_column(Integer, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=120)
    top_k: Mapped[int] = mapped_column(Integer, default=4)
    embedding_model: Mapped[str | None] = mapped_column(String(120))

    metrics: Mapped[list[str]] = mapped_column(JSON, default=list)
    metric_weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    judge_provider: Mapped[str | None] = mapped_column(String(40))
    judge_model: Mapped[str | None] = mapped_column(String(120))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    change_summary: Mapped[str | None] = mapped_column(Text)

    models: Mapped[list[ExperimentModel]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )
    runs: Mapped[list[EvaluationRun]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="EvaluationRun.created_at",
    )


class ExperimentModel(IDMixin, TimestampMixin, Base):
    __tablename__ = "experiment_models"

    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(160))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    experiment: Mapped[Experiment] = relationship(back_populates="models")

    @property
    def display(self) -> str:
        return self.label or f"{self.provider}/{self.model}"


class EvaluationRun(IDMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_runs"

    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    total_units: Mapped[int] = mapped_column(Integer, default=0)
    completed_units: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str | None] = mapped_column(String(48))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    experiment: Mapped[Experiment] = relationship(back_populates="runs")
    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(IDMixin, TimestampMixin, Base):
    """One test case executed against one model."""

    __tablename__ = "evaluation_results"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    experiment_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    test_case_id: Mapped[str] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    model_label: Mapped[str | None] = mapped_column(String(160))

    question: Mapped[str] = mapped_column(Text, default="")
    ground_truth: Mapped[str | None] = mapped_column(Text)
    generated_answer: Mapped[str | None] = mapped_column(Text)
    retrieved_context: Mapped[list[str]] = mapped_column(JSON, default=list)
    retrieval_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, index=True)
    composite_score: Mapped[float | None] = mapped_column(Float, index=True)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_kind: Mapped[str | None] = mapped_column(String(48), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
    metrics: Mapped[list[MetricResult]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )
    failure: Mapped[Failure | None] = relationship(
        back_populates="result", cascade="all, delete-orphan", uselist=False
    )

    @property
    def metric_map(self) -> dict[str, float | None]:
        return {m.metric: m.normalized_score for m in self.metrics}


class MetricResult(IDMixin, TimestampMixin, Base):
    __tablename__ = "metric_results"

    result_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_results.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="deterministic")  # deterministic|llm_judge|ragas|performance
    raw_score: Mapped[float | None] = mapped_column(Float)
    normalized_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    judge_model: Mapped[str | None] = mapped_column(String(160))
    evidence: Mapped[str | None] = mapped_column(Text)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    unavailable_reason: Mapped[str | None] = mapped_column(String(255))

    result: Mapped[EvaluationResult] = relationship(back_populates="metrics")


class Failure(IDMixin, TimestampMixin, Base):
    __tablename__ = "failures"

    result_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_results.id", ondelete="CASCADE"), index=True, nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    experiment_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    failure_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    detector: Mapped[str] = mapped_column(String(32), default="rule")  # rule|metric|provider
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    diagnosis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    diagnosed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diagnosis_source: Mapped[str | None] = mapped_column(String(32))  # llm|heuristic

    result: Mapped[EvaluationResult] = relationship(back_populates="failure")
