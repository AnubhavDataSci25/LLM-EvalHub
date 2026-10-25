"""Provider configuration and discovery endpoints. Never returns secrets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


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


@router.get("/{key}/models", summary="List models for a provider")
async def provider_models(key: str, db: DbSession) -> dict[str, Any]:
    return {"provider": key, "models": await ProviderService(db).models_for(key)}


@router.get("/{key}/health", summary="Check provider connectivity")
async def provider_health(key: str, db: DbSession) -> dict[str, Any]:
    return await ProviderService(db).health(key)
