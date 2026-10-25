"""Hugging Face Inference Providers adapter.

Uses the OpenAI-compatible router (https://router.huggingface.co/v1) so a single
HF token routes to whichever upstream inference provider serves the model.
"""

from __future__ import annotations

from app.core.config import settings
from app.providers.openai_compatible import OpenAICompatibleProvider


class HuggingFaceProvider(OpenAICompatibleProvider):
    key = "huggingface"
    display_name = "Hugging Face"
    kind = "gateway"
    paid_quota_possible = True
    docs_url = "https://huggingface.co/docs/inference-providers/"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key if api_key is not None else settings.hf_api_key,
            base_url=base_url or settings.hf_base_url,
        )
