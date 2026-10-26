"""Pydantic schemas for model availability audits."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AuditStatus = Literal[
    "AVAILABLE",
    "RATE_LIMITED",
    "NOT_ENTITLED",
    "NOT_FOUND",
    "INVALID_CREDENTIALS",
    "TIMEOUT",
    "UPSTREAM_ERROR",
    "EMPTY_RESPONSE",
    "NOT_PROBED",
]


class ProviderAuditRequest(BaseModel):
    providers: list[str] | None = Field(
        default=None, description="Optional subset of provider keys to audit"
    )
    max_probes_per_provider: int = Field(
        default=15, ge=1, le=50, description="Maximum number of model probes per provider"
    )
    dry_run: bool = Field(
        default=False, description="Estimate probe calls without executing generations"
    )


class ModelAvailabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model_id: str
    label: str | None = None
    status: AuditStatus | str
    reason: str
    checked_at: datetime
    latency_ms: float | None = None
    retry_after: float | None = None
    context_window: int | None = None
    tier: str | None = None
    is_stale: bool = False
    audit_run_id: str | None = None


class AuditRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    providers: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    items: list[ModelAvailabilityRead] = Field(default_factory=list)


class AuditDryRunResponse(BaseModel):
    dry_run: bool = True
    estimated_probes: int
    by_provider: dict[str, int]
    candidate_counts: dict[str, int]


class ProviderStatusSummary(BaseModel):
    provider: str
    display_name: str
    configured: bool
    listing_reachable: bool | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    last_audit_at: datetime | None = None
