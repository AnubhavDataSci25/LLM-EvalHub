"""Shared adapter for providers that speak the OpenAI Chat Completions wire format.

Verified against current provider documentation (Sept 2026):
  * Groq          -> https://api.groq.com/openai/v1
  * Hugging Face  -> https://router.huggingface.co/v1   (Inference Providers router)
  * OpenRouter    -> https://openrouter.ai/api/v1
  * NVIDIA NIM    -> https://integrate.api.nvidia.com/v1 (hosted) or any self-hosted NIM
  * Ollama        -> http://localhost:11434/v1          (optional, local)

Every base URL stays configurable so a self-hosted deployment can be pointed
somewhere else without code changes.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.exceptions import ProviderError, RateLimitedError
from app.core.logging import get_logger
from app.providers.base import GenerationRequest, LLMProvider, LLMResponse, ModelInfo

logger = get_logger(__name__)


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return (response.text or "").strip()[:500] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)[:500]
        if isinstance(err, str):
            return err[:500]
        if "detail" in payload:
            return str(payload["detail"])[:500]
        if "message" in payload:
            return str(payload["message"])[:500]
    return str(payload)[:500]


class OpenAICompatibleProvider(LLMProvider):
    """Chat-completions adapter with normalised errors, latency and usage."""

    supports_model_discovery: bool = True
    auth_scheme: str = "Bearer"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"{self.auth_scheme} {self.api_key}"
        return headers

    def _build_payload(self, request: GenerationRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        payload.update(request.extra or {})
        return payload

    def _translate_http_error(self, exc: httpx.HTTPStatusError) -> ProviderError:
        response = exc.response
        status = response.status_code
        message = _extract_error_message(response)
        if status == 429:
            return RateLimitedError(self.key, retry_after=_parse_retry_after(response))
        if status in (401, 403):
            return ProviderError(
                f"Authentication failed for provider '{self.key}': {message}",
                provider=self.key,
                kind="invalid_credentials",
                retryable=False,
                status=status,
            )
        if status == 404:
            return ProviderError(
                f"Model or endpoint not found on '{self.key}': {message}",
                provider=self.key,
                kind="model_unavailable",
                retryable=False,
                status=status,
            )
        if status in (402,):
            return ProviderError(
                f"Quota or payment required on '{self.key}': {message}",
                provider=self.key,
                kind="quota_exhausted",
                retryable=False,
                status=status,
            )
        if status >= 500:
            return ProviderError(
                f"Upstream error from '{self.key}': {message}",
                provider=self.key,
                kind="upstream_error",
                retryable=True,
                status=status,
            )
        return ProviderError(
            f"Request rejected by '{self.key}': {message}",
            provider=self.key,
            kind="bad_request",
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
        request = GenerationRequest(
            prompt=prompt,
            model=model,
            system_prompt=kwargs.get("system_prompt"),
            temperature=temperature,
            max_tokens=int(kwargs.get("max_tokens", 512)),
            timeout=kwargs.get("timeout") or self.default_timeout(),
            extra=kwargs.get("extra") or {},
        )
        payload = self._build_payload(request)
        url = f"{self.base_url}/chat/completions"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=request.timeout) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise self._translate_http_error(exc) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Provider '{self.key}' timed out after {request.timeout:.0f}s.",
                provider=self.key,
                kind="timeout",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Network error contacting '{self.key}': {exc}",
                provider=self.key,
                kind="network_error",
                retryable=True,
            ) from exc

        latency_ms = (time.perf_counter() - started) * 1000
        return self._parse_response(data, request, latency_ms)

    def _parse_response(
        self, data: dict[str, Any], request: GenerationRequest, latency_ms: float
    ) -> LLMResponse:
        choices = data.get("choices") or []
        text = ""
        finish_reason = None
        if choices:
            choice = choices[0] or {}
            finish_reason = choice.get("finish_reason")
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, list):  # some gateways return content parts
                text = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            else:
                text = content or ""
            if not text and message.get("reasoning"):
                text = str(message["reasoning"])
        usage_raw = data.get("usage") or {}
        usage = {
            "prompt_tokens": usage_raw.get("prompt_tokens"),
            "completion_tokens": usage_raw.get("completion_tokens"),
            "total_tokens": usage_raw.get("total_tokens"),
        }
        return LLMResponse(
            text=(text or "").strip(),
            provider=self.key,
            model=request.model,
            resolved_model=data.get("model") or request.model,
            latency_ms=latency_ms,
            usage={k: v for k, v in usage.items() if v is not None},
            finish_reason=finish_reason,
            raw_meta={
                "id": data.get("id"),
                "upstream_provider": data.get("provider"),
            },
        )

    async def discover_models(self) -> list[ModelInfo]:
        from app.providers.filtering import filter_chat_models

        if not self.supports_model_discovery or not self.is_configured:
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
            logger.warning("model discovery failed for %s: %s", self.key, exc)
            return []
        except httpx.HTTPError as exc:
            logger.warning("model discovery unreachable for %s: %s", self.key, exc)
            return []

        items = data.get("data") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []

        discovered: list[ModelInfo] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            mid = str(item.get("id"))
            label = str(item.get("name") or mid)
            context_window = item.get("context_length") or item.get("context_window")
            desc = item.get("description") or None
            arch = item.get("architecture") or {}
            modality = arch.get("modality") or "text->text"
            pricing = item.get("pricing") or {}
            tier = "free" if ":free" in mid or (pricing and pricing.get("prompt") == "0") else None

            discovered.append(
                ModelInfo(
                    id=mid,
                    provider=self.key,
                    label=label,
                    context_window=int(context_window) if context_window else None,
                    description=desc,
                    source="discovered",
                    modality=modality,
                    pricing=pricing,
                    tier=tier,
                )
            )

        chat_models, _ = filter_chat_models(discovered)
        return chat_models

    async def list_models(self) -> list[ModelInfo]:
        from app.providers.catalog import static_models

        fallback = static_models(self.key)
        if not self.supports_model_discovery or not self.is_configured:
            return fallback

        discovered = await self.discover_models()
        if not discovered:
            return fallback
        known = {m.id for m in discovered}
        discovered.extend(m for m in fallback if m.id not in known)
        return discovered
