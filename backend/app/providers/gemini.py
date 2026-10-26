"""Google Gemini adapter (native `generateContent` REST API).

Authentication uses the documented `x-goog-api-key` header. The native API is
preferred over the OpenAI-compatibility shim because it returns richer
`usageMetadata` and explicit safety/blocking information, both of which the
evaluation engine surfaces as evidence.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import ProviderError, RateLimitedError
from app.core.logging import get_logger
from app.providers.base import LLMProvider, LLMResponse, ModelInfo

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    key = "gemini"
    display_name = "Google Gemini"
    kind = "hosted"
    paid_quota_possible = True
    docs_url = "https://ai.google.dev/gemini-api/docs"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key if api_key is not None else settings.gemini_api_key,
            base_url=base_url or settings.gemini_base_url,
        )

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-goog-api-key": self.api_key or ""}

    def _translate_http_error(self, exc: httpx.HTTPStatusError) -> ProviderError:
        response = exc.response
        status = response.status_code
        try:
            payload = response.json()
            message = str((payload.get("error") or {}).get("message") or payload)[:500]
        except Exception:
            message = (response.text or f"HTTP {status}")[:500]

        if status == 429:
            retry_after = response.headers.get("retry-after")
            return RateLimitedError(
                self.key, retry_after=float(retry_after) if retry_after else None
            )
        if status in (401, 403):
            kind = "invalid_credentials"
        elif status == 404:
            kind = "model_unavailable"
        elif status >= 500:
            return ProviderError(
                f"Upstream error from Gemini: {message}",
                provider=self.key,
                kind="upstream_error",
                retryable=True,
                status=status,
            )
        else:
            kind = "bad_request"
        return ProviderError(
            f"Gemini request failed: {message}",
            provider=self.key,
            kind=kind,
            retryable=False,
            status=status,
        )

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        self.ensure_configured()
        timeout = float(kwargs.get("timeout") or self.default_timeout())
        system_prompt = kwargs.get("system_prompt")
        max_tokens = int(kwargs.get("max_tokens", 512))

        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        payload.update(kwargs.get("extra") or {})

        url = f"{self.base_url}/models/{model}:generateContent"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise self._translate_http_error(exc) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Gemini timed out after {timeout:.0f}s.",
                provider=self.key,
                kind="timeout",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Network error contacting Gemini: {exc}",
                provider=self.key,
                kind="network_error",
                retryable=True,
            ) from exc

        latency_ms = (time.perf_counter() - started) * 1000
        candidates = data.get("candidates") or []
        text = ""
        finish_reason = None
        if candidates:
            candidate = candidates[0] or {}
            finish_reason = candidate.get("finishReason")
            parts = (candidate.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))

        usage_meta = data.get("usageMetadata") or {}
        usage = {
            "prompt_tokens": usage_meta.get("promptTokenCount"),
            "completion_tokens": usage_meta.get("candidatesTokenCount"),
            "total_tokens": usage_meta.get("totalTokenCount"),
        }
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        return LLMResponse(
            text=text.strip(),
            provider=self.key,
            model=model,
            resolved_model=data.get("modelVersion") or model,
            latency_ms=latency_ms,
            usage={k: v for k, v in usage.items() if v is not None},
            finish_reason=finish_reason,
            raw_meta={"block_reason": block_reason} if block_reason else {},
        )

    async def discover_models(self) -> list[ModelInfo]:
        from app.providers.filtering import filter_chat_models

        if not self.is_configured:
            return []
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self.base_url}/models", headers=self._headers()
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise self._translate_http_error(exc) from exc
            logger.warning("gemini model discovery failed: %s", exc)
            return []
        except httpx.HTTPError as exc:
            logger.warning("gemini model discovery unreachable: %s", exc)
            return []

        models: list[ModelInfo] = []
        for item in data.get("models", []):
            name = str(item.get("name", "")).removeprefix("models/")
            methods = item.get("supportedGenerationMethods") or []
            if not name or (methods and "generateContent" not in methods):
                continue
            models.append(
                ModelInfo(
                    id=name,
                    provider=self.key,
                    label=item.get("displayName") or name,
                    context_window=item.get("inputTokenLimit"),
                    description=item.get("description"),
                    source="discovered",
                    modality="text->text",
                    tier="free",
                )
            )

        chat_models, _ = filter_chat_models(models)
        return chat_models

    async def list_models(self) -> list[ModelInfo]:
        from app.providers.catalog import static_models

        fallback = static_models(self.key)
        if not self.is_configured:
            return fallback

        discovered = await self.discover_models()
        if not discovered:
            return fallback
        known = {m.id for m in discovered}
        discovered.extend(m for m in fallback if m.id not in known)
        return discovered
