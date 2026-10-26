"""Optional local Ollama adapter.

Ollama is never required: the provider stays disabled unless OLLAMA_ENABLED=true.
The platform is designed to run entirely on hosted inference.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import ModelInfo
from app.providers.filtering import filter_chat_models
from app.providers.openai_compatible import OpenAICompatibleProvider

logger = get_logger(__name__)


class OllamaProvider(OpenAICompatibleProvider):
    key = "ollama"
    display_name = "Ollama (local, optional)"
    kind = "local"
    paid_quota_possible = False
    requires_api_key = False
    docs_url = "https://ollama.com/blog/openai-compatibility"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(api_key=api_key, base_url=base_url or settings.ollama_base_url)

    @property
    def is_configured(self) -> bool:
        return bool(settings.ollama_enabled and self.base_url)

    async def discover_models(self) -> list[ModelInfo]:
        """Discover locally installed models via Ollama's /api/tags endpoint."""
        if not self.is_configured:
            return []

        # Try native /api/tags endpoint first
        root_url = self.base_url.removesuffix("/v1")
        tags_url = f"{root_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(tags_url)
                if res.status_code == 200:
                    data = res.json()
                    models_raw = data.get("models") or []
                    discovered: list[ModelInfo] = []
                    for item in models_raw:
                        mid = str(item.get("name") or item.get("model") or "")
                        if not mid:
                            continue
                        details = item.get("details") or {}
                        desc = f"Local {details.get('parameter_size', '')} {details.get('family', '')} model".strip()
                        discovered.append(
                            ModelInfo(
                                id=mid,
                                provider=self.key,
                                label=mid,
                                description=desc or "Local Ollama model",
                                source="discovered",
                                modality="text->text",
                                tier="free",
                            )
                        )
                    chat_models, _ = filter_chat_models(discovered)
                    if chat_models:
                        return chat_models
        except Exception as exc:
            logger.debug("Ollama /api/tags unavailable (%s); falling back to /v1/models", exc)

        return await super().discover_models()

