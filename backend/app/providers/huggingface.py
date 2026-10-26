"""Hugging Face Inference Providers adapter.

Uses the OpenAI-compatible router (https://router.huggingface.co/v1) so a single
HF token routes to whichever upstream inference provider serves the model.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import ModelInfo
from app.providers.filtering import filter_chat_models
from app.providers.openai_compatible import OpenAICompatibleProvider

logger = get_logger(__name__)


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

    async def discover_models(self) -> list[ModelInfo]:
        """Discover live models served by Hugging Face Inference Providers.

        Verifies that candidates have active upstream serving providers before passing
        them to verification probes.
        """
        if not self.is_configured:
            return []
        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise self._translate_http_error(exc) from exc
            logger.warning("huggingface model discovery failed: %s", exc)
            return []
        except httpx.HTTPError as exc:
            logger.warning("huggingface model discovery unreachable: %s", exc)
            return []

        items = data.get("data") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []

        discovered: list[ModelInfo] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            mid = str(item.get("id"))

            # Check if any inference provider is actually live for this model
            providers_list = item.get("providers")
            if isinstance(providers_list, list) and len(providers_list) > 0:
                live_providers = [
                    p for p in providers_list if isinstance(p, dict) and p.get("status") == "live"
                ]
                if not live_providers:
                    # Not served by any live inference provider currently
                    continue
                context_window = max(
                    [p.get("context_length") for p in live_providers if p.get("context_length")]
                    or [None]
                )
                is_free = any(p.get("is_free") for p in live_providers)
            else:
                context_window = None
                is_free = False

            arch = item.get("architecture") or {}
            output_modalities = arch.get("output_modalities") or []
            if output_modalities and "text" not in output_modalities:
                continue

            discovered.append(
                ModelInfo(
                    id=mid,
                    provider=self.key,
                    label=mid,
                    context_window=int(context_window) if context_window else None,
                    description=f"Served by HF Inference Providers ({len(providers_list or [])} provider(s))",
                    source="discovered",
                    modality="text->text",
                    tier="free" if is_free else None,
                )
            )

        chat_models, _ = filter_chat_models(discovered)
        return chat_models

