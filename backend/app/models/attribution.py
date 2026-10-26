"""Counterfactual failure attribution models.

Stores empirical attribution runs and per-condition trial results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.experiment import Failure

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin


class AttributionRun(IDMixin, TimestampMixin, Base):
    """An empirical counterfactual attribution run for a failed work unit."""

    __tablename__ = "attribution_runs"

    failure_id: Mapped[str] = mapped_column(
        ForeignKey("failures.id", ondelete="CASCADE"), index=True, nullable=False
    )
    result_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_results.id", ondelete="CASCADE"), index=True, nullable=False
    )
    experiment_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    test_case_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)

    verdict: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    repeats: Mapped[int] = mapped_column(Integer, default=1)
    conditions_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="completed", index=True)
    error: Mapped[str | None] = mapped_column(Text)

    conditions: Mapped[list[AttributionCondition]] = relationship(
        back_populates="attribution_run",
        cascade="all, delete-orphan",
        order_by="AttributionCondition.condition, AttributionCondition.repeat_index",
    )
    failure: Mapped[Failure] = relationship("Failure", back_populates="attribution")


class AttributionCondition(IDMixin, TimestampMixin, Base):
    """Individual trial execution under one counterfactual condition."""

    __tablename__ = "attribution_conditions"

    attribution_run_id: Mapped[str] = mapped_column(
        ForeignKey("attribution_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    condition: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    repeat_index: Mapped[int] = mapped_column(Integer, default=0)

    context_text: Mapped[str | None] = mapped_column(Text)
    prompt_text: Mapped[str | None] = mapped_column(Text)
    generated_answer: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    error_kind: Mapped[str | None] = mapped_column(String(48))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    attribution_run: Mapped[AttributionRun] = relationship(back_populates="conditions")
