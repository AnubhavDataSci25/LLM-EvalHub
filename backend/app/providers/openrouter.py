"""OpenRouter adapter — unified gateway across many upstream model providers."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import GenerationRequest, LLMResponse
from app.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    key = "openrouter"
    display_name = "OpenRouter"
    kind = "gateway"
    paid_quota_possible = True
    docs_url = "https://openrouter.ai/docs"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key if api_key is not None else settings.openrouter_api_key,
            base_url=base_url or settings.openrouter_base_url,
        )

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        # Optional attribution headers documented by OpenRouter.
        headers["HTTP-Referer"] = settings.openrouter_site_url
        headers["X-Title"] = settings.openrouter_app_title
        return headers

    def _parse_response(
        self, data: dict[str, Any], request: GenerationRequest, latency_ms: float
    ) -> LLMResponse:
        response = super()._parse_response(data, request, latency_ms)
        # OpenRouter reports which upstream provider actually served the request.
        upstream = data.get("provider")
        if upstream:
            response.raw_meta["upstream_provider"] = upstream
        return response
