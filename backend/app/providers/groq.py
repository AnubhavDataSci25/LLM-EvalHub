"""Groq adapter — OpenAI-compatible endpoint at /openai/v1."""

from __future__ import annotations

from app.core.config import settings
from app.providers.openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    key = "groq"
    display_name = "Groq"
    kind = "hosted"
    paid_quota_possible = True
    docs_url = "https://console.groq.com/docs"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key if api_key is not None else settings.groq_api_key,
            base_url=base_url or settings.groq_base_url,
        )
