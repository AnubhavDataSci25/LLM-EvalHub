"""Health, metric catalogue, metadata, readiness and metrics endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import metrics_collector
from app.db.session import get_db
from app.evaluation.aggregators import DEFAULT_WEIGHTS
from app.evaluation.failure_detector import FAILURE_TYPES, FailureThresholds
from app.evaluation.ragas_adapter import ragas_available
from app.evaluation.registry import DEFAULT_METRICS, METRIC_SPECS, RAG_METRICS
from app.rag.vector_store import faiss_available
from app.schemas.common import HealthResponse
from app.services.audit_service import AuditService
from app.services.provider_service import ProviderService
from app.services.recommendation_service import PROFILE_DESCRIPTIONS, PROFILES

router = APIRouter(tags=["meta"])

VERSION = "1.0.0"


@router.get("/ready", summary="Service readiness, database, Redis and evaluator validation")
def ready(db: Session = Depends(get_db)) -> Response:
    # 1. Database check
    db_ok = False
    db_error = None
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)

    # 2. Redis check (only if configured)
    redis_status = "not_configured"
    redis_ok = True
    if settings.redis_url:
        try:
            import redis
            r = redis.from_url(settings.redis_url, socket_timeout=2.0)
            r.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "unreachable"
            redis_ok = False

    # 3. Default Evaluator check
    configured, total = ProviderService.configured_count()
    audit_svc = AuditService(db)
    evaluator_status = audit_svc.check_default_evaluator()

    evaluator_ready = evaluator_status.get("status") not in (
        "not_found",
        "not_entitled",
        "invalid_credentials",
        "unconfigured_provider",
    )

    payload = {
        "status": "ready" if (db_ok and redis_ok and evaluator_ready) else ("degraded" if (db_ok and redis_ok) else "unhealthy"),
        "app": settings.app_name,
        "version": VERSION,
        "environment": settings.app_env,
        "database": {
            "status": "connected" if db_ok else "unreachable",
            "type": "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
            "error": db_error,
        },
        "redis": {
            "status": redis_status,
        },
        "providers_configured": configured,
        "providers_total": total,
        "default_evaluator": evaluator_status,
    }

    if not db_ok or not redis_ok:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)

    return JSONResponse(status_code=status.HTTP_200_OK, content=payload)


@router.get("/health", response_model=HealthResponse, summary="Service liveness health check")
def health() -> HealthResponse:
    configured, total = ProviderService.configured_count()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=VERSION,
        environment=settings.app_env,
        database="postgresql" if settings.database_url.startswith("postgres") else "sqlite",
        providers_configured=configured,
        providers_total=total,
        optional_features={
            "ragas": ragas_available(),
            "faiss": faiss_available(),
            "llm_judge": settings.enable_llm_judge,
            "mock_provider": settings.enable_mock_provider,
            "metrics_enabled": settings.enable_metrics,
        },
    )


@router.get("/metrics", summary="Prometheus-compatible operational metrics")
def prometheus_metrics() -> Response:
    """Expose application metrics in Prometheus text exposition format."""
    if not settings.enable_metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics endpoint is disabled. Set ENABLE_METRICS=true to enable.",
        )
    return PlainTextResponse(
        metrics_collector.generate_prometheus_output(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/meta/metrics", summary="Metric catalogue")
def metrics_catalogue() -> dict[str, Any]:
    return {
        "metrics": [spec.as_dict() for spec in METRIC_SPECS.values()],
        "defaults": DEFAULT_METRICS,
        "rag_metrics": RAG_METRICS,
        "default_weights": DEFAULT_WEIGHTS,
    }


@router.get("/meta/failure-types", summary="Failure taxonomy and thresholds")
def failure_taxonomy() -> dict[str, Any]:
    return {
        "failure_types": [
            {"key": key, "label": key.replace("_", " ").title(), "description": description}
            for key, description in FAILURE_TYPES.items()
        ],
        "default_thresholds": FailureThresholds().as_dict(),
    }


@router.get("/meta/profiles", summary="Recommendation priority profiles")
def recommendation_profiles() -> dict[str, Any]:
    return {
        "profiles": [
            {"key": key, "weights": weights, "description": PROFILE_DESCRIPTIONS.get(key, "")}
            for key, weights in PROFILES.items()
        ],
    }
