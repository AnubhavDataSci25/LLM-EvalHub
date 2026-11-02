"""Durable background job management and execution service.

Supports two backends:
1. AsyncioJobBackend: In-process task runner (zero-dependency default for local SQLite development).
2. ArqJobBackend: Distributed queue worker backed by Redis and Arq (enabled when REDIS_URL is configured).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, RateLimitExceededError, ValidationFailedError
from app.core.logging import get_logger
from app.db.base import new_id
from app.db.session import session_scope
from app.models.experiment import EvaluationResult, EvaluationRun
from app.models.job import Job

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------
class JobBackend(ABC):
    """Abstract interface for background job execution."""

    @abstractmethod
    def register_cancellation(self, job_id: str) -> None:
        """Synchronously mark job as cancelled in memory."""

    @abstractmethod
    async def submit_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> None:
        """Submit a job for execution."""

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """Request job cancellation."""

    @abstractmethod
    def is_cancelled(self, job_id: str) -> bool:
        """Check whether a job has been requested to cancel."""


class AsyncioJobBackend(JobBackend):
    """In-process asyncio background job backend."""

    def __init__(self) -> None:
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._cancelled_jobs: set[str] = set()

    def register_cancellation(self, job_id: str) -> None:
        self._cancelled_jobs.add(job_id)

    async def submit_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> None:
        self._cancelled_jobs.discard(job_id)
        task = asyncio.create_task(self._dispatch_job(job_id, job_type, payload))
        self._active_tasks[job_id] = task
        task.add_done_callback(lambda _: self._active_tasks.pop(job_id, None))
        logger.info("Submitted asyncio job %s (type=%s)", job_id, job_type)

    async def cancel_job(self, job_id: str) -> bool:
        self.register_cancellation(job_id)
        logger.info("Job %s marked cancelled in AsyncioJobBackend", job_id)
        return True

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled_jobs

    async def _dispatch_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> None:
        if job_type == "evaluation_run":
            run_id = payload.get("run_id") or job_id
            from app.services.evaluation_service import EvaluationRunner

            runner = EvaluationRunner(run_id, job_id=job_id)
            await runner.execute()
        else:
            logger.warning("Unknown job type '%s' for job %s", job_type, job_id)


class ArqJobBackend(JobBackend):
    """Distributed Redis-backed job queue via Arq."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._cancelled_jobs: set[str] = set()
        self._fallback = AsyncioJobBackend()

    def register_cancellation(self, job_id: str) -> None:
        self._cancelled_jobs.add(job_id)
        self._fallback.register_cancellation(job_id)

    async def _get_pool(self) -> Any:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            return await create_pool(RedisSettings.from_dsn(self.redis_url))
        except Exception as exc:
            logger.warning("Could not connect to Redis (%s); falling back to in-process asyncio: %s", self.redis_url, exc)
            return None

    async def submit_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> None:
        self._cancelled_jobs.discard(job_id)
        pool = await self._get_pool()
        if pool is None:
            await self._fallback.submit_job(job_id, job_type, payload)
            return

        try:
            await pool.enqueue_job(job_type, job_id=job_id, payload=payload, _job_id=job_id)
            logger.info("Enqueued Arq job %s (type=%s) on Redis", job_id, job_type)
        finally:
            await pool.close()

    async def cancel_job(self, job_id: str) -> bool:
        self.register_cancellation(job_id)
        pool = await self._get_pool()
        if pool is not None:
            try:
                await pool.set(f"evalhub:cancel:{job_id}", "1", ex=86400)
            except Exception as exc:
                logger.warning("Failed setting cancellation key in Redis for %s: %s", job_id, exc)
            finally:
                await pool.close()
        return True

    def is_cancelled(self, job_id: str) -> bool:
        if job_id in self._cancelled_jobs:
            return True
        return self._fallback.is_cancelled(job_id)


_JOB_BACKEND_INSTANCE: JobBackend | None = None


def get_job_backend() -> JobBackend:
    """Returns singleton job backend according to application configuration."""
    global _JOB_BACKEND_INSTANCE
    if _JOB_BACKEND_INSTANCE is None:
        backend_kind = settings.effective_job_backend
        if backend_kind == "arq" and settings.redis_url:
            _JOB_BACKEND_INSTANCE = ArqJobBackend(settings.redis_url)
        else:
            _JOB_BACKEND_INSTANCE = AsyncioJobBackend()
    return _JOB_BACKEND_INSTANCE


def reset_job_backend_for_tests() -> None:
    """Reset singleton for deterministic testing."""
    global _JOB_BACKEND_INSTANCE
    _JOB_BACKEND_INSTANCE = None


# ---------------------------------------------------------------------------
# Job Service (database & lifecycle coordination)
# ---------------------------------------------------------------------------
class JobService:
    """Manages job persistence, concurrency limits, cancellation, and recovery."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def check_workspace_limits(self, workspace_id: str, incoming_units: int = 1) -> None:
        """Enforces per-workspace concurrent active job limits and daily call quotas."""
        # 1. Concurrent active jobs limit
        active_jobs_count = int(
            self.db.execute(
                select(func.count(Job.id)).where(
                    Job.workspace_id == workspace_id,
                    Job.status.in_(["queued", "running"]),
                )
            ).scalar_one()
        )
        if active_jobs_count >= settings.workspace_max_concurrent_jobs:
            raise RateLimitExceededError(
                f"Workspace concurrent job limit reached ({active_jobs_count}/{settings.workspace_max_concurrent_jobs} active). "
                "Please wait for existing runs to finish before starting a new one."
            )

        # 2. Daily call quota limit
        today_utc = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_calls = int(
            self.db.execute(
                select(func.count(EvaluationResult.id))
                .join(EvaluationRun, EvaluationResult.run_id == EvaluationRun.id)
                .where(
                    EvaluationRun.workspace_id == workspace_id,
                    EvaluationResult.created_at >= today_utc,
                )
            ).scalar_one()
        )
        if daily_calls + incoming_units > settings.workspace_daily_call_limit:
            raise RateLimitExceededError(
                f"Workspace daily LLM call limit reached ({daily_calls}/{settings.workspace_daily_call_limit} calls used today). "
                f"This run requests {incoming_units} calls. Quota resets at 00:00 UTC."
            )

    def create_job(
        self,
        *,
        workspace_id: str,
        job_type: str = "evaluation_run",
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
        total_units: int = 0,
        job_id: str | None = None,
    ) -> Job:
        """Create and persist a new Job row."""
        self.check_workspace_limits(workspace_id, incoming_units=max(1, total_units))
        jid = job_id or new_id("job")
        job = Job(
            id=jid,
            workspace_id=workspace_id,
            job_type=job_type,
            entity_id=entity_id,
            status="queued",
            progress=0.0,
            total_units=total_units,
            completed_units=0,
            failed_units=0,
            payload=payload or {},
            result={},
        )
        self.db.add(job)
        self.db.flush()
        from app.core.metrics import metrics_collector
        metrics_collector.record_job("queued")
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def get_job_or_404(self, job_id: str) -> Job:
        job = self.get_job(job_id)
        if not job:
            raise NotFoundError(f"Job '{job_id}' not found.")
        return job

    def list_jobs(
        self,
        workspace_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        stmt = select(Job).where(Job.workspace_id == workspace_id)
        if status:
            stmt = stmt.where(Job.status == status)
        total = int(self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
        stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all()), total

    def mark_running(self, job_id: str) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.status = "running"
            job.started_at = _utcnow()
            job.attempts += 1
            self.db.flush()
            from app.core.metrics import metrics_collector
            metrics_collector.record_job("running")

    def update_progress(
        self,
        job_id: str,
        *,
        completed_units: int,
        failed_units: int = 0,
        total_units: int | None = None,
    ) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.completed_units = completed_units
            job.failed_units = failed_units
            if total_units is not None:
                job.total_units = total_units
            total = max(1, job.total_units)
            job.progress = round(completed_units / total, 4)
            self.db.flush()

    def mark_succeeded(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.status = "succeeded"
            job.progress = 1.0
            job.completed_at = _utcnow()
            if result:
                job.result = result
            self.db.flush()
            from app.core.metrics import metrics_collector
            metrics_collector.record_job("succeeded")

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.status = "failed"
            job.last_error = error[:2000]
            job.completed_at = _utcnow()
            self.db.flush()
            from app.core.metrics import metrics_collector
            metrics_collector.record_job("failed")

    async def cancel_job(self, job_id: str) -> Job:
        """Mark job cancelled and signal worker."""
        job = self.get_job_or_404(job_id)
        if job.status in {"succeeded", "failed"}:
            raise ValidationFailedError(f"Cannot cancel job in '{job.status}' state.")

        job.status = "cancelled"
        job.completed_at = _utcnow()
        from app.core.metrics import metrics_collector
        metrics_collector.record_job("cancelled")

        if job.entity_id and job.job_type == "evaluation_run":
            run = self.db.get(EvaluationRun, job.entity_id)
            if run and run.status not in {"completed", "failed"}:
                run.status = "cancelled"
                run.stage = "cancelled"
                run.finished_at = _utcnow()

        self.db.flush()
        await get_job_backend().cancel_job(job.id)
        if job.entity_id:
            await get_job_backend().cancel_job(job.entity_id)
        return job

    async def resume_job(self, job_id: str) -> Job:
        """Resume an interrupted, cancelled, or failed job skipping completed units."""
        job = self.get_job_or_404(job_id)
        if job.status not in {"interrupted", "failed", "cancelled"}:
            raise ValidationFailedError(f"Only interrupted, failed or cancelled jobs can be resumed (current: '{job.status}').")

        # Check limits before resuming
        remaining_units = max(1, job.total_units - job.completed_units)
        self.check_workspace_limits(job.workspace_id, incoming_units=remaining_units)

        job.status = "queued"
        job.last_error = None

        if job.entity_id and job.job_type == "evaluation_run":
            run = self.db.get(EvaluationRun, job.entity_id)
            if run:
                run.status = "queued"
                run.stage = "queued"
                run.error = None

        self.db.flush()
        self.db.commit()

        await get_job_backend().submit_job(job.id, job.job_type, job.payload)
        return job

    @staticmethod
    def recover_interrupted_jobs() -> int:
        """On startup, mark orphaned running or queued jobs as interrupted."""
        with session_scope() as session:
            orphaned_jobs = list(
                session.execute(
                    select(Job).where(Job.status.in_(["queued", "running"]))
                ).scalars().all()
            )
            count = len(orphaned_jobs)
            for j in orphaned_jobs:
                j.status = "interrupted"
                j.last_error = "Server restart interrupted execution. Click Resume to continue."
                j.completed_at = _utcnow()
                if j.entity_id and j.job_type == "evaluation_run":
                    run = session.get(EvaluationRun, j.entity_id)
                    if run and run.status in {"queued", "running"}:
                        run.status = "interrupted"
                        run.stage = "interrupted"
                        run.error = "Run was interrupted due to server restart. Click Resume to continue."
                        run.finished_at = _utcnow()

            # Also check any EvaluationRuns without jobs that were orphaned in running state
            orphaned_runs = list(
                session.execute(
                    select(EvaluationRun).where(EvaluationRun.status.in_(["queued", "running"]))
                ).scalars().all()
            )
            for r in orphaned_runs:
                r.status = "interrupted"
                r.stage = "interrupted"
                r.error = "Run was interrupted due to server restart. Click Resume to continue."
                r.finished_at = _utcnow()

            if count or orphaned_runs:
                logger.info("Recovered %s orphaned jobs and %s orphaned runs -> marked interrupted", count, len(orphaned_runs))
            return count + len(orphaned_runs)
