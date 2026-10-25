"""Provider adapter contract tests. No network calls, no API keys required."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import NotFoundError, ProviderError, ProviderNotConfiguredError
from app.providers.base import LLMProvider
from app.providers.mock import MockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.registry import all_providers, get_provider, provider_keys


def test_every_registered_provider_implements_the_interface():
    for provider in all_providers():
        assert isinstance(provider, LLMProvider)
        assert provider.key and provider.display_name
        assert provider.kind in {"hosted", "gateway", "local"}
        described = provider.describe()
        assert set(described) >= {"key", "configured", "base_url", "kind"}


def test_describe_never_leaks_credentials():
    for provider in all_providers():
        assert "api_key" not in provider.describe()
        assert all("sk-" not in str(v) for v in provider.describe().values())


def test_unknown_provider_raises():
    with pytest.raises(NotFoundError):
        get_provider("does-not-exist")


def test_expected_providers_are_registered():
    keys = provider_keys()
    for expected in ("gemini", "groq", "huggingface", "openrouter", "nvidia_nim", "ollama", "mock"):
        assert expected in keys


@pytest.mark.asyncio
async def test_unconfigured_provider_raises_clear_error():
    provider = OpenAICompatibleProvider(api_key=None, base_url="https://example.invalid/v1")
    provider.key = "test-provider"
    with pytest.raises(ProviderNotConfiguredError):
        await provider.generate("hello", "some-model")


@pytest.mark.asyncio
async def test_mock_provider_is_deterministic():
    provider = MockProvider()
    prompt = "Context:\nRefunds are available within 30 days.\n\nQuestion: What is the refund window?"
    first = await provider.generate(prompt, "mock-extractive")
    second = await provider.generate(prompt, "mock-extractive")
    assert first.text == second.text
    assert "30 days" in first.text
    assert first.latency_ms > 0
    assert first.usage["total_tokens"] > 0


@pytest.mark.asyncio
async def test_mock_behaviours_are_selectable():
    provider = MockProvider()
    prompt = "Context:\nA fact.\n\nQuestion: What?"
    assert (await provider.generate(prompt, "mock-empty")).is_empty
    with pytest.raises(ProviderError) as timeout:
        await provider.generate(prompt, "mock-timeout")
    assert timeout.value.kind == "timeout" and timeout.value.retryable is True
    with pytest.raises(ProviderError) as upstream:
        await provider.generate(prompt, "mock-error")
    assert upstream.value.retryable is True


@pytest.mark.asyncio
async def test_http_errors_map_to_typed_provider_errors(monkeypatch):
    """429 -> retryable rate limit; 401 -> non-retryable credential error."""
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="https://example.invalid/v1")
    provider.key = "test-provider"

    def make_response(status: int, body: dict, headers: dict | None = None):
        request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        return httpx.Response(status, json=body, headers=headers or {}, request=request)

    async def post_429(self, url, **kwargs):
        return make_response(429, {"error": {"message": "slow down"}}, {"retry-after": "3"})

    monkeypatch.setattr(httpx.AsyncClient, "post", post_429)
    with pytest.raises(ProviderError) as exc:
        await provider.generate("hi", "m")
    assert exc.value.kind == "rate_limited"
    assert exc.value.retryable is True
    assert exc.value.retry_after == 3.0

    async def post_401(self, url, **kwargs):
        return make_response(401, {"error": {"message": "bad key"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", post_401)
    with pytest.raises(ProviderError) as exc:
        await provider.generate("hi", "m")
    assert exc.value.kind == "invalid_credentials"
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_successful_response_is_normalised(monkeypatch):
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="https://example.invalid/v1")
    provider.key = "test-provider"

    async def post_ok(self, url, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "id": "resp-1",
                "model": "resolved-model",
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": "  Hello  "}}
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post_ok)
    response = await provider.generate("hi", "requested-model", temperature=0.2, max_tokens=64)
    assert response.text == "Hello"
    assert response.resolved_model == "resolved-model"
    assert response.usage["total_tokens"] == 7
    assert response.finish_reason == "stop"
    assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_timeouts_are_retryable(monkeypatch):
    provider = OpenAICompatibleProvider(api_key="k", base_url="https://example.invalid/v1")
    provider.key = "test-provider"

    async def post_timeout(self, url, **kwargs):
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(httpx.AsyncClient, "post", post_timeout)
    with pytest.raises(ProviderError) as exc:
        await provider.generate("hi", "m")
    assert exc.value.kind == "timeout" and exc.value.retryable is True
