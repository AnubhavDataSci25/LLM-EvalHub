"""Provider abstraction.

Every provider exposes the same internal contract:

    generate(prompt, model, ...) -> LLMResponse
    list_models() -> list[ModelInfo]
    health() -> ProviderHealth

The evaluation engine depends on this interface only; nothing downstream of
`providers/` knows whether a response came from Groq, Gemini or a local Ollama
server. Adding a provider therefore never requires an architectural change.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.exceptions import ProviderError


@dataclass(slots=True)
class LLMResponse:
    """Normalised generation result."""

    text: str
    provider: str
    model: str
    latency_ms: float
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None
    resolved_model: str | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.text or "").strip()


@dataclass(slots=True)
class ModelInfo:
    id: str
    provider: str
    label: str | None = None
    context_window: int | None = None
    description: str | None = None
    source: str = "catalog"  # catalog | discovered
    modality: str = "text->text"
    pricing: dict[str, Any] = field(default_factory=dict)
    tier: str | None = None  # free | paid | enterprise
    status: str = "unverified"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "label": self.label or self.id,
            "context_window": self.context_window,
            "description": self.description,
            "source": self.source,
            "modality": self.modality,
            "pricing": self.pricing,
            "tier": self.tier,
            "status": self.status,
        }


@dataclass(slots=True)
class ProviderHealth:
    provider: str
    configured: bool
    reachable: bool | None
    message: str
    checked_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class GenerationRequest:
    prompt: str
    model: str
    system_prompt: str | None = None
    temperature: float = 0.0
    max_tokens: int = 512
    timeout: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(abc.ABC):
    """Abstract provider adapter."""

    #: stable machine key, e.g. "groq"
    key: str = "base"
    #: human label shown in the UI
    display_name: str = "Base provider"
    #: "hosted" | "gateway" | "local"
    kind: str = "hosted"
    #: whether usage on this route may require paid quota
    paid_quota_possible: bool = True
    requires_api_key: bool = True
    docs_url: str = ""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = (base_url or "").rstrip("/")

    # -- configuration ---------------------------------------------------
    @property
    def api_key(self) -> str | None:
        return self._api_key

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_configured(self) -> bool:
        if not self.requires_api_key:
            return bool(self._base_url)
        return bool(self._api_key)

    def ensure_configured(self) -> None:
        if not self.is_configured:
            from app.core.exceptions import ProviderNotConfiguredError

            raise ProviderNotConfiguredError(self.key)

    # -- contract --------------------------------------------------------
    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a single completion. Must raise `ProviderError` on failure."""

    async def list_models(self) -> list[ModelInfo]:
        """Return known models. Providers that support discovery should override."""
        from app.providers.catalog import static_models

        return static_models(self.key)

    async def discover_models(self) -> list[ModelInfo]:
        """Discover live models directly from the provider's API.

        Queries the provider's model listing endpoint and filters to chat/text-generation models.
        """
        return await self.list_models()

    async def health(self) -> ProviderHealth:
        if not self.is_configured:
            return ProviderHealth(
                provider=self.key,
                configured=False,
                reachable=None,
                message="No credentials configured for this provider.",
            )
        try:
            models = await self.list_models()
            return ProviderHealth(
                provider=self.key,
                configured=True,
                reachable=True,
                message=f"Reachable. {len(models)} model(s) available.",
            )
        except ProviderError as exc:
            return ProviderHealth(
                provider=self.key, configured=True, reachable=False, message=exc.message
            )

    # -- helpers ---------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "kind": self.kind,
            "configured": self.is_configured,
            "requires_api_key": self.requires_api_key,
            "paid_quota_possible": self.paid_quota_possible,
            "base_url": self.base_url,
            "docs_url": self.docs_url,
        }

    @staticmethod
    def default_timeout() -> float:
        return float(settings.request_timeout_seconds)
