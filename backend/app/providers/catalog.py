"""Fallback model catalog.

These are *starting points* shown when live model discovery is unavailable (no
API key yet, or the provider does not expose `/models`). They are hints for the
UI only — they are never treated as a performance ranking, and the model field
is always user-editable. Live discovery from the provider always wins.

Model availability changes frequently; anything here may be superseded by the
provider's own `/models` response.
"""

from __future__ import annotations

from app.providers.base import ModelInfo

_CATALOG: dict[str, list[tuple[str, str]]] = {
    "gemini": [
        ("gemini-3-flash-preview", "Fast general-purpose frontier model (audited live)"),
        ("gemini-3.1-flash-lite", "Lowest latency tier (audited live)"),
        ("gemini-2.5-pro", "Highest capability frontier tier"),
        ("gemini-2.5-flash", "Previous generation workhorse"),
    ],
    "groq": [
        ("openai/gpt-oss-120b", "Open-weight MoE (audited live)"),
        ("qwen/qwen3.8-27b", "Multilingual open model (audited live)"),
        ("allam-2-7b", "Fast open instruct model (audited live)"),
        ("openai/gpt-oss-20b", "Compact open model (audited live)"),
        ("llama-3.1-8b-instant", "Small, very low latency"),
    ],
    "huggingface": [
        ("meta-llama/Llama-3.3-70B-Instruct", "Routed via Inference Providers"),
        ("meta-llama/Llama-3.1-8B-Instruct", "Small instruct model"),
        ("deepseek-ai/DeepSeek-R1", "Reasoning-oriented model"),
        ("openai/gpt-oss-120b", "Open-weight MoE"),
    ],
    "openrouter": [
        ("meta-llama/llama-3.3-70b-instruct", "Routed across upstream providers (audited live)"),
        ("google/gemma-3-27b-it", "Open Google model (audited live)"),
        ("mistralai/mistral-small-3.2-24b-instruct", "Efficient mid-size model (audited live)"),
        ("qwen/qwen3-30b-a3b-instruct", "Open MoE model"),
    ],
    "nvidia_nim": [
        ("meta/llama-3.3-70b-instruct", "NIM-hosted Llama"),
        ("meta/llama-3.1-8b-instruct", "Small NIM-hosted Llama"),
        ("nvidia/llama-3.1-nemotron-nano-8b-v1", "NVIDIA Nemotron nano"),
        ("openai/gpt-oss-120b", "Open-weight MoE on NIM"),
        ("qwen/qwen3-next-80b-a3b-instruct", "Large open MoE on NIM"),
    ],
    "ollama": [
        ("llama3.2:3b", "Local small model"),
        ("qwen2.5:3b", "Local small model"),
        ("phi3:mini", "Local tiny model"),
    ],
}


def static_models(provider: str) -> list[ModelInfo]:
    return [
        ModelInfo(
            id=mid,
            provider=provider,
            label=mid,
            description=desc,
            source="catalog",
            status="unverified",
        )
        for mid, desc in _CATALOG.get(provider, [])
    ]


def default_model(provider: str) -> str | None:
    entries = _CATALOG.get(provider)
    return entries[0][0] if entries else None
