"""Audit log service for recording and retrieving security actions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.audit_log import AuditLog

logger = get_logger(__name__)


class AuditLogService:
    """Service for capturing and querying workspace audit logs."""

    @staticmethod
    def log(
        session: Session,
        *,
        workspace_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id: str | None = None,
        actor_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
        details: dict[str, Any] | None = None,
    ) -> AuditLog | None:
        """Create and persist an audit log entry."""
        try:
            log_entry = AuditLog(
                id=f"aud_{uuid.uuid4().hex[:16]}",
                workspace_id=workspace_id,
                user_id=user_id,
                actor_email=actor_email,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details or {},
            )
            session.add(log_entry)
            session.flush()
            logger.info(
                "Audit: workspace=%s action=%s resource=%s/%s status=%s",
                workspace_id,
                action,
                resource_type,
                resource_id or "-",
                status,
            )
            return log_entry
        except Exception as exc:
            logger.error("Failed to write audit log entry: %s", exc)
            return None

    @staticmethod
    def list_logs(
        session: Session,
        workspace_id: str,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """Query paginated audit logs for a workspace."""
        query = select(AuditLog).where(AuditLog.workspace_id == workspace_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)

        count_query = select(func.count()).select_from(query.subquery())
        total = session.execute(count_query).scalar_one()

        items_query = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
        items = list(session.execute(items_query).scalars().all())

        return items, total
