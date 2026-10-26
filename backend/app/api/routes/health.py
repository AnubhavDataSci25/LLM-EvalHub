"""Health, metric catalogue and metadata endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
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


@router.get("/ready", summary="Service readiness and default evaluator validation")
def ready(db: Session = Depends(get_db)) -> dict[str, Any]:
    configured, total = ProviderService.configured_count()
    audit_svc = AuditService(db)
    evaluator_status = audit_svc.check_default_evaluator()

    is_ready = True
    if evaluator_status.get("status") in (
        "not_found",
        "not_entitled",
        "invalid_credentials",
        "unconfigured_provider",
    ):
        is_ready = False

    return {
        "status": "ready" if is_ready else "degraded",
        "app": settings.app_name,
        "version": VERSION,
        "environment": settings.app_env,
        "database": "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
        "providers_configured": configured,
        "providers_total": total,
        "default_evaluator": evaluator_status,
    }


@router.get("/health", response_model=HealthResponse, summary="Service health")
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
        },
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
        ]
        + [{"key": "custom", "weights": {}, "description": PROFILE_DESCRIPTIONS["custom"]}]
    }
