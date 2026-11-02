export const addingProviderSection = {
  id: 'adding-provider',
  title: 'Developer Guide: Adding a Provider',
  group: 'Technical reference',
  summary: 'Step-by-step developer tutorial for integrating a new LLM provider adapter into the evaluation engine without modifying downstream services.',
  blocks: [
    {
      type: 'paragraph',
      text: 'Because of the strict provider abstraction layer, adding a new foundation model provider touches exactly two files: the new provider adapter and the provider registry. The rest of the platform (evaluators, LangGraph workflows, comparison math, database schemas) is completely provider-agnostic.',
    },
    {
      type: 'heading',
      id: 'step-1-adapter',
      level: 2,
      text: 'Step 1: Implement the LLMProvider Interface',
    },
    {
      type: 'paragraph',
      text: 'Create a new file in `backend/app/providers/custom.py`. If the provider supports an OpenAI-compatible wire protocol (like vLLM, DeepInfra, Mistral, or Together AI), subclass `OpenAICompatibleProvider` to inherit streaming, token counting, and error mapping automatically. Otherwise, subclass `LLMProvider` directly:',
    },
    {
      type: 'code',
      language: 'python',
      filename: 'backend/app/providers/custom.py',
      code: `"""Custom provider adapter."""
from __future__ import annotations

import httpx
from app.core.exceptions import ProviderError
from app.providers.base import LLMProvider, LLMResponse, ModelInfo, ProviderHealth

class CustomProvider(LLMProvider):
    key = "custom"
    label = "Custom Provider"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.custom-ai.com/v1"

    async def generate(
        self,
        prompt: str,
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 500,
        system_prompt: str | None = None,
        timeout: float = 60.0,
    ) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt or ""},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]
                return LLMResponse(
                    text=choice["message"]["content"],
                    provider=self.key,
                    model=model,
                    latency_ms=120.0,
                    finish_reason=choice.get("finish_reason"),
                )
            except httpx.HTTPStatusError as exc:
                # Map upstream errors into typed ProviderError
                kind = "rate_limited" if exc.response.status_code == 429 else "upstream_error"
                raise ProviderError(str(exc), provider=self.key, status_code=exc.response.status_code, kind=kind)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="custom-70b", provider=self.key, label="Custom 70B")]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(configured=bool(self.api_key), provider=self.key)

    def describe(self) -> dict:
        return {"key": self.key, "label": self.label, "configured": bool(self.api_key)}`,
    },
    {
      type: 'heading',
      id: 'step-2-register',
      level: 2,
      text: 'Step 2: Register in the Provider Registry',
    },
    {
      type: 'paragraph',
      text: 'Open `backend/app/providers/registry.py` and register your class:',
    },
    {
      type: 'code',
      language: 'python',
      filename: 'backend/app/providers/registry.py',
      code: `from app.providers.custom import CustomProvider

# Add to _PROVIDER_CLASSES
_PROVIDER_CLASSES[CustomProvider.key] = CustomProvider

# Add to PROVIDER_ORDER for UI display sorting
if CustomProvider.key not in PROVIDER_ORDER:
    PROVIDER_ORDER.append(CustomProvider.key)`,
    },
    {
      type: 'heading',
      id: 'step-3-test',
      level: 2,
      text: 'Step 3: Add Automated Unit Tests',
    },
    {
      type: 'paragraph',
      text: 'Write a unit test in `backend/tests/` asserting that `get_provider("custom")` resolves your adapter and that error mapping correctly translates HTTP 429 to `rate_limited` and 401 to `invalid_credentials`.',
    },
  ],
}
