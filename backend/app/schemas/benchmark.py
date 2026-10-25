"""Benchmark pack schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BenchmarkPackSummary(BaseModel):
    key: str
    name: str
    description: str
    use_case: str
    metrics: list[str]
    case_count: int
    rag_recommended: bool = False
    difficulty_mix: dict[str, int] = Field(default_factory=dict)
    categories: list[str] = Field(default_factory=list)
    default_config: dict[str, Any] = Field(default_factory=dict)
    metric_notes: dict[str, str] = Field(default_factory=dict)
    installed_dataset_id: str | None = None


class BenchmarkPackDetail(BenchmarkPackSummary):
    sample_cases: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkInstallRequest(BaseModel):
    dataset_name: str | None = None
    create_experiment: bool = False
    models: list[dict[str, str]] = Field(default_factory=list)
