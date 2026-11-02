"""Background worker entrypoint for LLM-EvalHub.

Can be run directly via:
    python -m app.worker
or via Arq CLI:
    arq app.worker.WorkerSettings
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_db
from app.services.evaluation_service import EvaluationRunner
from app.services.jobs import JobService

logger = get_logger(__name__)


async def run_evaluation_job(ctx: dict[str, Any], job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Worker task handler for evaluation runs."""
    run_id = payload.get("run_id") or job_id
    logger.info("Worker starting evaluation job %s (run_id=%s)", job_id, run_id)
    runner = EvaluationRunner(run_id, job_id=job_id)
    await runner.execute()
    return {"status": "completed", "job_id": job_id, "run_id": run_id}


async def startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook."""
    configure_logging()
    init_db()
    recovered = JobService.recover_interrupted_jobs()
    logger.info("Worker started (recovered %s interrupted jobs)", recovered)


async def shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook."""
    logger.info("Worker shutting down")


class WorkerSettings:
    """Arq worker configuration."""

    functions = [run_evaluation_job]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 3600

    @classmethod
    def get_redis_settings(cls) -> Any:
        try:
            from arq.connections import RedisSettings

            return RedisSettings.from_dsn(settings.redis_url or "redis://localhost:6379/0")
        except Exception:
            return None

    redis_settings = get_redis_settings()


def main() -> None:
    """Standalone worker entrypoint."""
    configure_logging()
    if settings.effective_job_backend == "arq" and settings.redis_url:
        try:
            from arq import run_worker

            logger.info("Starting Arq worker with Redis at %s", settings.redis_url)
            run_worker(WorkerSettings)
        except Exception as exc:
            logger.error("Failed to start Arq worker: %s", exc)
    else:
        logger.info("No REDIS_URL configured; running standalone monitor & recovery")
        init_db()
        recovered = JobService.recover_interrupted_jobs()
        print(f"Standalone worker initialized. Recovered {recovered} jobs. Press Ctrl+C to exit.")
        try:
            asyncio.run(asyncio.sleep(3600 * 24 * 365))
        except (KeyboardInterrupt, SystemExit):
            pass


if __name__ == "__main__":
    main()
