"""Authentication and multi-tenant workspace data models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import Recommendation, Report
    from app.models.audit_log import AuditLog
    from app.models.dataset import Dataset, Document
    from app.models.experiment import EvaluationRun, Experiment
    from app.models.job import Job


class User(IDMixin, TimestampMixin, Base):
    """User account."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    memberships: Mapped[list[WorkspaceMember]] = relationship(
        "WorkspaceMember", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class Workspace(IDMixin, TimestampMixin, Base):
    """Isolated tenant workspace. Datasets, experiments, and documents belong to exactly one workspace."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list[WorkspaceMember]] = relationship(
        "WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan"
    )
    provider_keys: Mapped[list[WorkspaceProviderKey]] = relationship(
        "WorkspaceProviderKey", back_populates="workspace", cascade="all, delete-orphan"
    )

    # Scoped child resources
    datasets: Mapped[list[Dataset]] = relationship(
        "Dataset", back_populates="workspace", cascade="all, delete-orphan"
    )
    experiments: Mapped[list[Experiment]] = relationship(
        "Experiment", back_populates="workspace", cascade="all, delete-orphan"
    )
    evaluation_runs: Mapped[list[EvaluationRun]] = relationship(
        "EvaluationRun", back_populates="workspace", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="workspace", cascade="all, delete-orphan"
    )
    reports: Mapped[list[Report]] = relationship(
        "Report", back_populates="workspace", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        "Recommendation", back_populates="workspace", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        "Job", back_populates="workspace", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(IDMixin, TimestampMixin, Base):
    """Membership connecting a User to a Workspace with a role."""

    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(32), default="editor", nullable=False
    )  # owner | editor | viewer

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="members")
    user: Mapped[User] = relationship("User", back_populates="memberships")


class RefreshToken(IDMixin, TimestampMixin, Base):
    """Hashed rotating refresh token."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    replaced_by: Mapped[str | None] = mapped_column(String(128))

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class WorkspaceProviderKey(IDMixin, TimestampMixin, Base):
    """Fernet-encrypted API key configured per workspace for a specific provider."""

    __tablename__ = "workspace_provider_keys"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_workspace_provider_key"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(16), nullable=False)

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="provider_keys")
