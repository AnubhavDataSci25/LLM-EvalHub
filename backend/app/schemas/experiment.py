"""Experiment / evaluation / analysis schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.evaluation.registry import DEFAULT_METRICS, METRIC_SPECS


class ModelSelection(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=160)
    label: str | None = Field(default=None, max_length=160)
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def display(self) -> str:
        return self.label or f"{self.provider}/{self.model}"


class RAGConfig(BaseModel):
    enabled: bool = False
    collection: str | None = None
    retriever: Literal["vector", "keyword", "hybrid"] = "vector"
    chunk_size: int = Field(default=800, ge=120, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    top_k: int = Field(default=4, ge=1, le=20)
    embedding_backend: str | None = None

    @model_validator(mode="after")
    def _check_collection(self) -> RAGConfig:
        if self.enabled and not (self.collection or "").strip():
            raise ValueError("A document collection is required when RAG is enabled.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self


class JudgeConfigIn(BaseModel):
    provider: str | None = None
    model: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.provider and self.model)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    dataset_id: str
    dataset_version_id: str | None = None
    models: list[ModelSelection] = Field(min_length=1)
    metrics: list[str] = Field(default_factory=lambda: list(DEFAULT_METRICS))
    metric_weights: dict[str, float] = Field(default_factory=dict)
    system_prompt: str | None = Field(default=None, max_length=8000)
    prompt_template: str | None = Field(default=None, max_length=8000)
    prompt_label: str = Field(default="v1", max_length=40)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=16, le=8192)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    judge: JudgeConfigIn = Field(default_factory=JudgeConfigIn)
    tags: list[str] = Field(default_factory=list)
    parent_experiment_id: str | None = None
    origin: Literal["manual", "benchmark", "improvement"] = "manual"
    benchmark_pack_key: str | None = None
    change_summary: str | None = None

    @field_validator("metrics")
    @classmethod
    def _known_metrics(cls, values: list[str]) -> list[str]:
        unknown = [v for v in values if v not in METRIC_SPECS]
        if unknown:
            raise ValueError(f"Unknown metric(s): {', '.join(unknown)}")
        return values or list(DEFAULT_METRICS)

    @field_validator("metric_weights")
    @classmethod
    def _valid_weights(cls, weights: dict[str, float]) -> dict[str, float]:
        for key, value in weights.items():
            if key not in METRIC_SPECS:
                raise ValueError(f"Unknown metric in weights: {key}")
            if value < 0:
                raise ValueError("Metric weights must be non-negative.")
        return weights


class ExperimentModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model: str
    label: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    dataset_id: str
    dataset_version_id: str
    dataset_name: str | None = None
    parent_experiment_id: str | None = None
    origin: str
    benchmark_pack_key: str | None = None
    system_prompt: str | None = None
    prompt_template: str = ""
    prompt_label: str = "v1"
    temperature: float
    max_tokens: int
    rag_enabled: bool
    rag_collection: str | None = None
    retriever: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    embedding_model: str | None = None
    metrics: list[str] = Field(default_factory=list)
    metric_weights: dict[str, float] = Field(default_factory=dict)
    judge_provider: str | None = None
    judge_model: str | None = None
    tags: list[str] = Field(default_factory=list)
    change_summary: str | None = None
    models: list[ExperimentModelRead] = Field(default_factory=list)
    created_at: datetime
    run_count: int = 0
    latest_run_id: str | None = None
    latest_run_status: str | None = None
    latest_summary: dict[str, Any] = Field(default_factory=dict)


class RunEvaluationRequest(BaseModel):
    """Either reference an existing experiment, or define one inline."""

    experiment_id: str | None = None
    experiment: ExperimentCreate | None = None
    case_ids: list[str] | None = Field(
        default=None, description="Optional subset of test cases to run."
    )
    latency_budget_ms: float = Field(default=4000.0, gt=0)

    @model_validator(mode="after")
    def _one_of(self) -> RunEvaluationRequest:
        if not self.experiment_id and not self.experiment:
            raise ValueError("Provide either experiment_id or an inline experiment definition.")
        return self


class MetricResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric: str
    kind: str
    raw_score: float | None = None
    normalized_score: float | None = None
    confidence: float | None = None
    judge_model: str | None = None
    evidence: str | None = None
    available: bool = True
    unavailable_reason: str | None = None


class FailureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    result_id: str
    run_id: str
    experiment_id: str
    failure_type: str
    severity: str
    detector: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)
    diagnosis: dict[str, Any] | None = None
    diagnosed_at: datetime | None = None
    diagnosis_source: str | None = None
    created_at: datetime


class EvaluationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    experiment_id: str
    test_case_id: str
    provider: str
    model: str
    model_label: str | None = None
    question: str
    ground_truth: str | None = None
    generated_answer: str | None = None
    retrieved_context: list[str] = Field(default_factory=list)
    retrieval_meta: dict[str, Any] = Field(default_factory=dict)
    status: str
    passed: bool | None = None
    latency_ms: float | None = None
    composite_score: float | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    error_kind: str | None = None
    error_message: str | None = None
    raw_meta: dict[str, Any] = Field(default_factory=dict)
    metrics: list[MetricResultRead] = Field(default_factory=list)
    failure: FailureRead | None = None


class EvaluationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    experiment_name: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    status: str
    progress: float
    total_units: int
    completed_units: int
    stage: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ComparisonRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=6)
    baseline_run_id: str | None = None
    metrics: list[str] | None = None


class DiagnoseRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    force: bool = False


class ImprovementRequest(BaseModel):
    """Turn a diagnosis/recommendation into a concrete follow-up experiment."""

    name: str | None = None
    run_id: str | None = None
    failure_ids: list[str] = Field(default_factory=list)
    apply: dict[str, Any] = Field(
        default_factory=dict,
        description="Overrides, e.g. {'top_k': 6, 'system_prompt': '...', 'models': [...]}",
    )
    rerun_failed_only: bool = True
    auto_run: bool = True
    change_summary: str | None = None


class RecommendationRequest(BaseModel):
    use_case: str = Field(default="general", max_length=120)
    profile: Literal["balanced", "quality", "faithfulness", "latency", "custom"] = "balanced"
    weights: dict[str, float] = Field(default_factory=dict)
    run_ids: list[str] = Field(default_factory=list)
    dataset_id: str | None = None
    experiment_ids: list[str] = Field(default_factory=list)
    max_latency_ms: float | None = Field(default=None, gt=0)
    min_faithfulness: float | None = Field(default=None, ge=0, le=1)
    min_correctness: float | None = Field(default=None, ge=0, le=1)
    max_failure_rate: float | None = Field(default=None, ge=0, le=1)
    providers: list[str] = Field(default_factory=list)
    min_sample_size: int = Field(default=3, ge=1)


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    use_case: str
    profile: str
    scope: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    recommended_provider: str | None = None
    recommended_model: str | None = None
    recommended_score: float | None = None
    rationale: str | None = None
    evidence: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    sample_size: int = 0
    created_at: datetime


class ReportRequest(BaseModel):
    run_id: str
    baseline_run_id: str | None = None
    title: str | None = None
    include_failures: bool = True
    max_failures: int = Field(default=25, ge=1, le=200)
    include_recommendation: bool = True


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    run_id: str | None = None
    experiment_id: str | None = None
    baseline_run_id: str | None = None
    kind: str
    content: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ProviderModelRead(BaseModel):
    id: str
    provider: str
    label: str
    context_window: int | None = None
    description: str | None = None
    source: str = "catalog"


class ProviderRead(BaseModel):
    key: str
    display_name: str
    kind: str
    configured: bool
    requires_api_key: bool
    paid_quota_possible: bool
    base_url: str
    docs_url: str
    env_var: str | None = None
    status: str = "unknown"
    message: str | None = None
    models: list[ProviderModelRead] = Field(default_factory=list)
