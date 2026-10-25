"""Provider inspection service.

Only non-secret information ever leaves the backend: whether a provider is
configured, its base URL, and the models it exposes. API keys are never
returned, logged or echoed.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.registry import all_providers, get_provider, provider_keys

logger = get_logger(__name__)

ENV_VARS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "huggingface": "HF_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "ollama": "OLLAMA_ENABLED / OLLAMA_BASE_URL",
    "mock": "ENABLE_MOCK_PROVIDER",
}

PROVIDER_NOTES = {
    "mock": "Deterministic fixture used for tests and offline development. Its outputs are "
            "mechanical, not model generations, and must not be read as benchmark results.",
    "ollama": "Optional. The platform never requires local inference; enable only if you run Ollama.",
    "nvidia_nim": "Works with NVIDIA-hosted NIM or a self-hosted NIM endpoint via NVIDIA_NIM_BASE_URL.",
    "openrouter": "Gateway across many upstream models. Not every model is free — check your account.",
    "huggingface": "Routes to whichever inference provider serves the model; quota depends on that provider.",
}


class ProviderService:
    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def describe_all(self) -> list[dict[str, Any]]:
        blocks = []
        for provider in all_providers():
            block = provider.describe()
            block["env_var"] = ENV_VARS.get(provider.key)
            block["note"] = PROVIDER_NOTES.get(provider.key)
            block["status"] = "configured" if provider.is_configured else "not_configured"
            block["message"] = (
                None
                if provider.is_configured
                else f"Set {ENV_VARS.get(provider.key, 'the provider key')} in the backend .env file."
            )
            block["models"] = []
            blocks.append(block)
        return blocks

    async def describe_with_models(self, *, check_health: bool = False) -> list[dict[str, Any]]:
        blocks = self.describe_all()

        async def hydrate(block: dict[str, Any]) -> None:
            provider = get_provider(block["key"])
            if not provider.is_configured:
                from app.providers.catalog import static_models

                block["models"] = [m.as_dict() for m in static_models(provider.key)]
                return
            try:
                models = await asyncio.wait_for(provider.list_models(), timeout=25)
                block["models"] = [m.as_dict() for m in models]
                block["status"] = "ready"
                block["message"] = f"{len(models)} model(s) available."
            except ProviderError as exc:
                block["status"] = "error"
                block["message"] = exc.message
            except TimeoutError:
                block["status"] = "error"
                block["message"] = "Model discovery timed out."
            except Exception as exc:  # pragma: no cover
                block["status"] = "error"
                block["message"] = str(exc)[:200]

        await asyncio.gather(*(hydrate(b) for b in blocks))
        return blocks

    async def models_for(self, key: str) -> list[dict[str, Any]]:
        provider = get_provider(key)
        models = await provider.list_models()
        return [m.as_dict() for m in models]

    async def health(self, key: str) -> dict[str, Any]:
        provider = get_provider(key)
        health = await provider.health()
        return {
            "provider": health.provider,
            "configured": health.configured,
            "reachable": health.reachable,
            "message": health.message,
        }

    @staticmethod
    def configured_count() -> tuple[int, int]:
        keys = provider_keys()
        configured = sum(1 for p in all_providers() if p.is_configured)
        return configured, len(keys)

    @staticmethod
    def runtime_settings() -> dict[str, Any]:
        """Non-secret runtime configuration shown on the settings page."""
        return {
            "environment": settings.app_env,
            "max_concurrent_requests": settings.max_concurrent_requests,
            "request_timeout_seconds": settings.request_timeout_seconds,
            "retry_attempts": settings.retry_attempts,
            "max_dataset_rows": settings.max_dataset_rows,
            "max_upload_mb": round(settings.max_upload_bytes / 1e6, 1),
            "enable_llm_judge": settings.enable_llm_judge,
            "enable_ragas": settings.enable_ragas,
            "embedding_backend": settings.embedding_backend,
            "vector_store_backend": settings.vector_store_backend,
            "default_chunk_size": settings.default_chunk_size,
            "default_chunk_overlap": settings.default_chunk_overlap,
            "default_top_k": settings.default_top_k,
            "database": "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
        }
