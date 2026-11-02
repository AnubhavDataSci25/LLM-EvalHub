"""Background job endpoints for monitoring, cancellation, and resumption."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentWorkspaceContext, DbSession, PageParams
from app.core.exceptions import NotFoundError
from app.schemas.job import JobListResponse, JobRead
from app.services.jobs import JobService

jobs_router = APIRouter(prefix="/jobs", tags=["jobs"])


@jobs_router.get("", response_model=JobListResponse, summary="List background jobs")
def list_jobs(
    db: DbSession,
    page: PageParams,
    ctx: CurrentWorkspaceContext,
    status: str | None = Query(None),
) -> dict[str, Any]:
    service = JobService(db)
    items, total = service.list_jobs(
        workspace_id=ctx.workspace.id,
        status=status,
        limit=page.limit,
        offset=page.offset,
    )
    return {
        "items": [JobRead.model_validate(j) for j in items],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@jobs_router.get("/{job_id}", response_model=JobRead, summary="Get background job status")
def get_job(
    job_id: str,
    db: DbSession,
    ctx: CurrentWorkspaceContext,
) -> JobRead:
    service = JobService(db)
    job = service.get_job_or_404(job_id)
    if job.workspace_id != ctx.workspace.id:
        raise NotFoundError(f"Job '{job_id}' not found.")
    return JobRead.model_validate(job)


@jobs_router.post("/{job_id}/cancel", response_model=JobRead, summary="Cancel background job")
async def cancel_job(
    job_id: str,
    db: DbSession,
    ctx: CurrentWorkspaceContext,
) -> JobRead:
    ctx.require_role("editor")
    service = JobService(db)
    job = service.get_job_or_404(job_id)
    if job.workspace_id != ctx.workspace.id:
        raise NotFoundError(f"Job '{job_id}' not found.")
    cancelled = await service.cancel_job(job_id)
    return JobRead.model_validate(cancelled)


@jobs_router.post("/{job_id}/resume", response_model=JobRead, summary="Resume background job")
async def resume_job(
    job_id: str,
    db: DbSession,
    ctx: CurrentWorkspaceContext,
) -> JobRead:
    ctx.require_role("editor")
    service = JobService(db)
    job = service.get_job_or_404(job_id)
    if job.workspace_id != ctx.workspace.id:
        raise NotFoundError(f"Job '{job_id}' not found.")
    resumed = await service.resume_job(job_id)
    return JobRead.model_validate(resumed)
