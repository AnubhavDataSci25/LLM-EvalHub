"""Dashboard/analytics schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KpiBlock(BaseModel):
    datasets: int = 0
    test_cases: int = 0
    experiments: int = 0
    evaluation_runs: int = 0
    completed_runs: int = 0
    results: int = 0
    failures: int = 0
    documents: int = 0
    avg_quality_score: float | None = None
    avg_correctness: float | None = None
    avg_faithfulness: float | None = None
    avg_answer_relevance: float | None = None
    avg_latency_ms: float | None = None
    failure_rate: float | None = None
    error_rate: float | None = None
    diagnosed_failures: int = 0
    judge_calibration: dict[str, Any] = Field(
        default_factory=lambda: {"calibrated": False, "kappa": None, "n_labels": 0}
    )


class DashboardResponse(BaseModel):
    kpis: KpiBlock
    judge_calibration: dict[str, Any] = Field(
        default_factory=lambda: {"calibrated": False, "kappa": None, "n_labels": 0}
    )
    model_comparison: list[dict[str, Any]] = Field(default_factory=list)
    metric_trend: list[dict[str, Any]] = Field(default_factory=list)
    failure_distribution: list[dict[str, Any]] = Field(default_factory=list)
    latency_distribution: list[dict[str, Any]] = Field(default_factory=list)
    score_distribution: list[dict[str, Any]] = Field(default_factory=list)
    recent_runs: list[dict[str, Any]] = Field(default_factory=list)
    provider_status: list[dict[str, Any]] = Field(default_factory=list)
    experiment_deltas: list[dict[str, Any]] = Field(default_factory=list)
    empty: bool = True
