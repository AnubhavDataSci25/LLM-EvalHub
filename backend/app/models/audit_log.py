"""Audit log model for security and operational events."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin


class AuditLog(IDMixin, TimestampMixin, Base):
    """Immutable audit log record for workspace security operations."""

    __tablename__ = "audit_logs"

    workspace_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    workspace: Mapped[Any] = relationship("Workspace", back_populates="audit_logs")
    user: Mapped[Any] = relationship("User")

    __table_args__ = (
        Index("ix_audit_logs_workspace_action", "workspace_id", "action"),
        Index("ix_audit_logs_workspace_created", "workspace_id", "created_at"),
    )
