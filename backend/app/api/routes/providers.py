"""Provider configuration, discovery, and availability audit endpoints. Never returns secrets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.core.exceptions import NotFoundError
from app.models.audit import AuditRun
from app.schemas.audit import (
    ProviderAuditRequest,
)
from app.services.audit_service import AuditService
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


async def _run_audit_background(
    run_id: str, providers: list[str] | None, max_probes: int
) -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        service = AuditService(session)
        await service.execute_audit(run_id, providers, max_probes)


@router.get("", summary="List providers")
async def list_providers(
    db: DbSession,
    with_models: bool = Query(False, description="Also fetch each provider's model list"),
) -> dict[str, Any]:
    service = ProviderService(db)
    providers = (
        await service.describe_with_models() if with_models else service.describe_all()
    )
    return {"providers": providers, "runtime": service.runtime_settings()}


@router.get("/status", summary="Provider availability status summary")
async def provider_status(db: DbSession) -> list[dict[str, Any]]:
    """Summarises per provider: key configured, listing reachable, counts per status, last audit time.

    NEVER returns API keys.
    """
    return AuditService(db).get_provider_status_summaries()


@router.get("/models", summary="List verified available models across providers")
async def available_models(
    db: DbSession,
    include_limited: bool = Query(
        False, description="Include temporarily rate-limited models"
    ),
    include_unavailable: bool = Query(
        False, description="Include all models regardless of status (diagnostics/settings only)"
    ),
) -> dict[str, Any]:
    """Returns ONLY AVAILABLE models by default, grouped by provider.

    Each model includes last_checked_at and probe latency_ms.
    """
    grouped = AuditService(db).get_available_models_grouped(
        include_limited=include_limited, include_unavailable=include_unavailable
    )
    return {"models": grouped, "providers": grouped}


@router.post("/audit", summary="Trigger a model availability audit")
async def run_audit(
    payload: ProviderAuditRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Runs a model availability audit.

    Supports dry_run to estimate provider call counts without executing probes.
    """
    service = AuditService(db)
    target_providers = payload.providers or [p["key"] for p in ProviderService(db).describe_all()]

    if payload.dry_run:
        est = await service.estimate_audit_calls(
            target_providers, payload.max_probes_per_provider
        )
        return est

    audit_run = await service.execute_audit(
        target_providers=target_providers,
        max_probes_per_provider=payload.max_probes_per_provider,
    )

    items = [
        {
            "id": item.id,
            "provider": item.provider,
            "model_id": item.model_id,
            "status": item.status,
            "reason": item.reason,
            "checked_at": item.checked_at.isoformat(),
            "latency_ms": item.latency_ms,
            "retry_after": item.retry_after,
            "context_window": item.context_window,
            "tier": item.tier,
        }
        for item in audit_run.availabilities
    ]

    return {
        "id": audit_run.id,
        "audit_run_id": audit_run.id,
        "status": audit_run.status,
        "providers": audit_run.providers,
        "summary": audit_run.summary,
        "items": items,
        "max_probes_per_provider": payload.max_probes_per_provider,
    }


@router.get("/audit/{audit_id}", summary="Get audit run status and results")
async def get_audit(audit_id: str, db: DbSession) -> dict[str, Any]:
    audit_run = db.get(AuditRun, audit_id)
    if not audit_run:
        raise NotFoundError(f"AuditRun '{audit_id}' was not found.")

    items = [
        {
            "id": item.id,
            "provider": item.provider,
            "model_id": item.model_id,
            "status": item.status,
            "reason": item.reason,
            "checked_at": item.checked_at.isoformat(),
            "latency_ms": item.latency_ms,
            "retry_after": item.retry_after,
            "context_window": item.context_window,
            "tier": item.tier,
        }
        for item in audit_run.availabilities
    ]

    return {
        "id": audit_run.id,
        "status": audit_run.status,
        "providers": audit_run.providers,
        "summary": audit_run.summary,
        "dry_run": audit_run.dry_run,
        "created_at": audit_run.created_at.isoformat() if audit_run.created_at else None,
        "completed_at": audit_run.completed_at.isoformat() if audit_run.completed_at else None,
        "error": audit_run.error,
        "items": items,
    }


@router.post("/{key}/models/{model_id:path}/recheck", summary="Re-check a specific model")
async def recheck_model(key: str, model_id: str, db: DbSession) -> dict[str, Any]:
    service = AuditService(db)
    rec = await service.recheck_model(key, model_id)
    return {
        "id": rec.id,
        "provider": rec.provider,
        "model_id": rec.model_id,
        "status": rec.status,
        "reason": rec.reason,
        "checked_at": rec.checked_at.isoformat(),
        "latency_ms": rec.latency_ms,
        "retry_after": rec.retry_after,
        "item": {
            "id": rec.id,
            "provider": rec.provider,
            "model_id": rec.model_id,
            "status": rec.status,
            "reason": rec.reason,
            "checked_at": rec.checked_at.isoformat(),
            "latency_ms": rec.latency_ms,
            "retry_after": rec.retry_after,
        },
    }


@router.get("/{key}/models", summary="List models for a provider")
async def provider_models(key: str, db: DbSession) -> dict[str, Any]:
    return {"provider": key, "models": await ProviderService(db).models_for(key)}


@router.get("/{key}/health", summary="Check provider connectivity")
async def provider_health(key: str, db: DbSession) -> dict[str, Any]:
    return await ProviderService(db).health(key)
