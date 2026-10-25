"""SQLAlchemy models for human labels and judge calibration runs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin


class HumanLabel(IDMixin, TimestampMixin, Base):
    __tablename__ = "human_labels"
    __table_args__ = (
        UniqueConstraint(
            "result_id", "metric", "annotator", name="uq_human_label_result_metric_annotator"
        ),
    )

    result_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_results.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    label: Mapped[int] = mapped_column(Integer, nullable=False)  # 0: incorrect, 1: partial, 2: correct
    annotator: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    result: Mapped[Any] = relationship("EvaluationResult")


class CalibrationRun(IDMixin, TimestampMixin, Base):
    __tablename__ = "calibration_runs"

    judge_provider: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    judge_model: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    metric: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    n_labels: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    agreement: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    probes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
