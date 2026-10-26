"""Schemas for Counterfactual Failure Attribution."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttributionRequest(BaseModel):
    """Payload to trigger counterfactual attribution for a single failure."""

    model_config = ConfigDict(extra="forbid")

    repeats: int = Field(default=1, ge=1, le=5, description="Number of repeats per counterfactual condition.")
    include_distractor: bool = Field(
        default=False, description="Whether to include the DISTRACTOR_ONLY counterfactual condition."
    )


class BatchAttributionRequest(BaseModel):
    """Payload to trigger batch attribution for an experiment."""

    model_config = ConfigDict(extra="forbid")

    max_cases: int = Field(
        default=10, ge=1, le=50, description="Maximum number of failed cases to attribute (capped to protect quota)."
    )
    categories: list[str] | None = Field(
        default=None, description="Optional list of failure types to include (e.g., ['poor_retrieval'])."
    )
    repeats: int = Field(default=1, ge=1, le=5, description="Repeats per condition.")
    dry_run: bool = Field(
        default=False, description="When true, returns only the estimated number of provider calls without running."
    )
    include_distractor: bool = Field(default=False)


class AttributionConditionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    condition: str
    repeat_index: int = 0
    context_text: str | None = None
    generated_answer: str | None = None
    latency_ms: float | None = None
    scores: dict[str, Any] = Field(default_factory=dict)
    passed: bool | None = None
    error_kind: str | None = None
    error_message: str | None = None


class AttributionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    failure_id: str
    result_id: str
    experiment_id: str
    run_id: str
    test_case_id: str
    verdict: str
    confidence: float
    reason: str
    evidence: list[str] = Field(default_factory=list)
    repeats: int = 1
    conditions_summary: dict[str, Any] = Field(default_factory=dict)
    recommendation: str
    status: str
    error: str | None = None
    created_at: str | None = None
    conditions: list[AttributionConditionRead] = Field(default_factory=list)


class AttributionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    experiment_id: str
    total_failures: int
    total_attributed: int
    verdict_counts: dict[str, int]
    retrieval_share: float
    generation_share: float
    items: list[AttributionRunRead] = Field(default_factory=list)


class BatchAttributionResponse(BaseModel):
    dry_run: bool
    experiment_id: str
    target_cases: int
    total_failures: int
    estimated_provider_calls: int
    conditions_per_case: int | None = None
    repeats: int | None = None
    max_cases: int | None = None
    completed_cases: int | None = None
    items: list[AttributionRunRead] | None = None
