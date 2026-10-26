"""Provider registry.

Adding a provider = implement `LLMProvider` + register it here. No other layer
of the application needs to change.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.exceptions import NotFoundError
from app.providers.base import LLMProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.huggingface import HuggingFaceProvider
from app.providers.mock import MockProvider
from app.providers.nvidia_nim import NvidiaNIMProvider
from app.providers.ollama import OllamaProvider
from app.providers.openrouter import OpenRouterProvider

_PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    GeminiProvider.key: GeminiProvider,
    GroqProvider.key: GroqProvider,
    HuggingFaceProvider.key: HuggingFaceProvider,
    OpenRouterProvider.key: OpenRouterProvider,
    NvidiaNIMProvider.key: NvidiaNIMProvider,
    OllamaProvider.key: OllamaProvider,
    MockProvider.key: MockProvider,
}

#: order used for UI listing
PROVIDER_ORDER = [
    "groq",
    "gemini",
    "huggingface",
    "openrouter",
    "nvidia_nim",
    "ollama",
    "mock",
]


def register_provider(cls: type[LLMProvider]) -> None:
    _PROVIDER_CLASSES[cls.key] = cls
    if cls.key not in PROVIDER_ORDER:
        PROVIDER_ORDER.append(cls.key)


def provider_keys() -> list[str]:
    return [k for k in PROVIDER_ORDER if k in _PROVIDER_CLASSES]


def is_provider_registered(key: str) -> bool:
    return key in _PROVIDER_CLASSES


def get_provider(key: str) -> LLMProvider:
    """Build a provider adapter. Credentials are read from settings at build time."""
    cls = _PROVIDER_CLASSES.get(key)
    if cls is None:
        raise NotFoundError(f"Unknown provider '{key}'.")
    return cls()


def all_providers() -> Iterable[LLMProvider]:
    for key in provider_keys():
        yield get_provider(key)


def configured_providers() -> list[LLMProvider]:
    return [p for p in all_providers() if p.is_configured]
