"""Recommendations, reports and comparison artefacts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IDMixin, TimestampMixin


class Recommendation(IDMixin, TimestampMixin, Base):
    """A stored model recommendation, always tied to measured evidence."""

    __tablename__ = "recommendations"

    use_case: Mapped[str] = mapped_column(String(120), default="general")
    profile: Mapped[str] = mapped_column(String(40), default="balanced")
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recommended_provider: Mapped[str | None] = mapped_column(String(40))
    recommended_model: Mapped[str | None] = mapped_column(String(160))
    recommended_score: Mapped[float | None] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    caveats: Mapped[list[str]] = mapped_column(JSON, default=list)
    sample_size: Mapped[int] = mapped_column(default=0)


class Report(IDMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(48), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(48), index=True)
    baseline_run_id: Mapped[str | None] = mapped_column(String(48), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="evaluation")
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProviderConfigRecord(IDMixin, TimestampMixin, Base):
    """Non-secret, user-visible provider preferences (default models, enabled flag)."""

    __tablename__ = "provider_configs"

    provider: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    default_model: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    last_checked_status: Mapped[str | None] = mapped_column(String(32))
    last_checked_message: Mapped[str | None] = mapped_column(Text)
