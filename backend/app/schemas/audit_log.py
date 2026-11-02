"""Audit log Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    """Public read model for an audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str | None = None
    actor_email: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    status: str
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: list[AuditLogRead]
    total: int
    limit: int
    offset: int
