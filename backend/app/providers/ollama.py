"""Optional local Ollama adapter.

Ollama is never required: the provider stays disabled unless OLLAMA_ENABLED=true.
The platform is designed to run entirely on hosted inference.
"""

from __future__ import annotations

from app.core.config import settings
from app.providers.openai_compatible import OpenAICompatibleProvider


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
