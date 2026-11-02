"""Pydantic schemas for durable background jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    job_type: str
    entity_id: str | None = None
    status: str
    progress: float = 0.0
    total_units: int = 0
    completed_units: int = 0
    failed_units: int = 0
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobListResponse(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int
