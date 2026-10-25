"""NVIDIA NIM adapter.

NIM exposes OpenAI-compatible `/v1/chat/completions`. The base URL is fully
configurable so the same adapter serves NVIDIA-hosted endpoints
(https://integrate.api.nvidia.com/v1) and self-hosted NIM containers.
Local/self-hosted NIM is never assumed or required.
"""

from __future__ import annotations

from app.core.config import settings
from app.providers.openai_compatible import OpenAICompatibleProvider


class NvidiaNIMProvider(OpenAICompatibleProvider):
    key = "nvidia_nim"
    display_name = "NVIDIA NIM"
    kind = "hosted"
    paid_quota_possible = True
    docs_url = "https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key if api_key is not None else settings.nvidia_nim_api_key,
            base_url=base_url or settings.nvidia_nim_base_url,
        )

    @property
    def is_configured(self) -> bool:
        # A self-hosted NIM deployment may not require a key; a base URL is enough
        # when it is not the NVIDIA-hosted default.
        if self.api_key:
            return True
        return bool(self.base_url) and "integrate.api.nvidia.com" not in self.base_url
