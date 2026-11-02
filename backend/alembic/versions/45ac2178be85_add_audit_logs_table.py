"""add_audit_logs_table

Revision ID: 45ac2178be85
Revises: a9528080e203
Create Date: 2026-10-28 18:50:28.989812

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "45ac2178be85"
down_revision: str | Sequence[str] | None = "a9528080e203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to add audit_logs table."""
    op.create_table(
        "audit_logs",
        sa.Column("workspace_id", sa.String(length=48), nullable=False),
        sa.Column("user_id", sa.String(length=48), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_logs_action"), ["action"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_resource_type"), ["resource_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_user_id"), ["user_id"], unique=False)
        batch_op.create_index("ix_audit_logs_workspace_action", ["workspace_id", "action"], unique=False)
        batch_op.create_index("ix_audit_logs_workspace_created", ["workspace_id", "created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_workspace_id"), ["workspace_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema by dropping audit_logs table."""
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_workspace_id"))
        batch_op.drop_index("ix_audit_logs_workspace_created")
        batch_op.drop_index("ix_audit_logs_workspace_action")
        batch_op.drop_index(batch_op.f("ix_audit_logs_user_id"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_resource_type"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_created_at"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_action"))

    op.drop_table("audit_logs")
