"""Model availability and audit run models.

Stores probe results, machine-readable status, latency, and audit history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin


class AuditRun(IDMixin, TimestampMixin, Base):
    """Execution of a model availability audit job."""

    __tablename__ = "audit_runs"

    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    providers: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    availabilities: Mapped[list[ModelAvailability]] = relationship(
        "ModelAvailability",
        back_populates="audit_run",
        cascade="all, delete-orphan",
        order_by="ModelAvailability.provider, ModelAvailability.model_id",
    )

    @property
    def items(self) -> list[ModelAvailability]:
        return self.availabilities


class ModelAvailability(IDMixin, TimestampMixin, Base):
    """Empirical availability status for a provider + model."""

    __tablename__ = "model_availability"

    provider: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    latency_ms: Mapped[float | None] = mapped_column(Float)
    retry_after: Mapped[float | None] = mapped_column(Float)
    audit_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="SET NULL"), index=True
    )
    context_window: Mapped[int | None] = mapped_column(Integer)
    tier: Mapped[str | None] = mapped_column(String(32))
    raw_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    audit_run: Mapped[AuditRun | None] = relationship(
        "AuditRun", back_populates="availabilities"
    )
