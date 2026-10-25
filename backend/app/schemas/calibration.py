"""Pydantic schemas for judge calibration and human labelling."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LabelUpsertRequest(BaseModel):
    result_id: str
    metric: str
    label: int = Field(ge=0, le=2, description="0=incorrect, 1=partially correct, 2=correct")
    annotator: str = Field(default="default", max_length=64)
    note: str | None = None

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"correctness", "faithfulness", "answer_relevance"}:
            raise ValueError(
                f"Metric '{v}' is not a calibratable judge metric. "
                "Must be one of: correctness, faithfulness, answer_relevance."
            )
        return clean


class HumanLabelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    result_id: str
    metric: str
    label: int
    annotator: str
    note: str | None = None
    created_at: datetime


class QueueItemRead(BaseModel):
    result_id: str
    run_id: str
    model: str
    model_label: str | None = None
    question: str
    expected_answer: str | None = None
    generated_answer: str | None = None
    retrieved_context: list[str] = Field(default_factory=list)
    metric: str


class CalibrationRunRequest(BaseModel):
    run_id: str | None = None
    dataset_id: str | None = None
    metric: str = "correctness"
    judge_provider: str | None = None
    judge_model: str | None = None
    run_probes: bool = True

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"correctness", "faithfulness", "answer_relevance"}:
            raise ValueError(
                f"Metric '{v}' is not a calibratable judge metric. "
                "Must be one of: correctness, faithfulness, answer_relevance."
            )
        return clean


class CalibrationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    judge_provider: str
    judge_model: str
    metric: str
    scope: dict[str, Any] = Field(default_factory=dict)
    n_labels: int = 0
    status: str
    agreement: dict[str, Any] = Field(default_factory=dict)
    probes: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class ReliabilityResponse(BaseModel):
    calibrated: bool = False
    status: str = "uncalibrated"
    judge_provider: str | None = None
    judge_model: str | None = None
    metric: str | None = None
    kappa: float | None = None
    weighted_kappa: float | None = None
    interval: tuple[float, float] | list[float] | None = None
    n_labels: int = 0
    interpretation: str | None = None
    agreement: dict[str, Any] = Field(default_factory=dict)
    probes: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
