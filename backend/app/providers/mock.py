"""Deterministic local provider used for tests, CI and offline development.

This provider is **not** a simulation of a real model and the UI labels it as a
test fixture. It exists so that the full pipeline
(dataset -> generation -> evaluation -> persistence) can be exercised without a
paid API key, exactly as required by the testing strategy.

Behaviour is purely mechanical and documented:

* if context is supplied, it extracts the sentence most lexically similar to the
  question (an extractive baseline),
* otherwise it echoes a short deterministic acknowledgement,
* seeded degradations can be requested via the model id suffix so failure paths
  (`empty`, `timeout`, `error`, `hallucinate`) are testable.

Nothing produced here is ever presented as a benchmark result for a real model.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.providers.base import LLMProvider, LLMResponse, ModelInfo

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


class MockProvider(LLMProvider):
    key = "mock"
    display_name = "Deterministic test provider"
    kind = "local"
    paid_quota_possible = False
    requires_api_key = False
    docs_url = ""

    #: behaviour switches encoded in the model id, e.g. "mock-extractive:empty"
    BEHAVIOURS = (
        "extractive",
        "empty",
        "timeout",
        "error",
        "verbose",
        "hallucinate",
        "judge",
        "oracle_only",
        "always_fail",
        "parametric",
        "context_free",
        "rate_limited",
        "not_entitled",
        "not_found",
        "invalid_credentials",
        "upstream_error",
        "empty_response",
        "available",
        "embed_text",
        "guard_classifier",
    )

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(api_key=api_key, base_url=base_url or "local://mock")

    @property
    def is_configured(self) -> bool:
        return bool(settings.enable_mock_provider)

    @classmethod
    def _behaviour(cls, model: str) -> str:
        """Resolve the behaviour switch from the model id (`mock-<behaviour>`)."""
        token = model.split(":")[-1] if ":" in model else model
        token = token.removeprefix("mock-").strip().lower().replace("-", "_")
        return token if token in cls.BEHAVIOURS else "extractive"

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        self.ensure_configured()
        behaviour = self._behaviour(model)
        started = time.perf_counter()
        await asyncio.sleep(0.005)

        if behaviour == "timeout":
            raise ProviderError(
                "Deterministic test provider simulated a timeout.",
                provider=self.key,
                kind="timeout",
                retryable=True,
            )
        if behaviour in ("error", "upstream_error"):
            raise ProviderError(
                "Deterministic test provider simulated an upstream failure.",
                provider=self.key,
                kind="upstream_error",
                status=503,
                retryable=True,
            )
        if behaviour == "rate_limited":
            from app.core.exceptions import RateLimitedError

            raise RateLimitedError(self.key, retry_after=30.0)
        if behaviour == "not_entitled":
            raise ProviderError(
                "Plan restricted: Enterprise tier or payment required for this model.",
                provider=self.key,
                kind="quota_exhausted",
                status=403,
                retryable=False,
            )
        if behaviour == "not_found":
            raise ProviderError(
                "Model 'mock-not-found' does not exist or has been retired.",
                provider=self.key,
                kind="model_unavailable",
                status=404,
                retryable=False,
            )
        if behaviour == "invalid_credentials":
            raise ProviderError(
                "Authentication failed: invalid test credentials.",
                provider=self.key,
                kind="invalid_credentials",
                status=401,
                retryable=False,
            )
        if behaviour in ("empty", "empty_response"):
            text = ""
        else:
            text = self._answer(prompt, behaviour)

        latency_ms = (time.perf_counter() - started) * 1000
        digest = hashlib.sha256(f"{model}|{prompt}".encode()).hexdigest()[:12]
        return LLMResponse(
            text=text,
            provider=self.key,
            model=model,
            resolved_model=model,
            latency_ms=latency_ms,
            usage={
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(text.split()),
                "total_tokens": len(prompt.split()) + len(text.split()),
            },
            finish_reason="stop",
            raw_meta={"deterministic": True, "digest": digest, "behaviour": behaviour},
        )

    # -- extractive baseline ---------------------------------------------
    @staticmethod
    def _split_prompt(prompt: str) -> tuple[str, str]:
        """Split the rendered prompt into (context, question) using our markers."""
        context, question = "", prompt
        if "Question:" in prompt:
            head, _, tail = prompt.rpartition("Question:")
            question = tail.strip()
            context = head
        if "Context:" in context:
            context = context.split("Context:", 1)[1]
        return context.strip(), question.strip()

    def _answer(self, prompt: str, behaviour: str) -> str:
        if behaviour == "judge":
            digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            h = int(digest, 16)
            scores = [0.0, 0.25, 0.5, 0.75, 1.0]
            chosen_score = scores[h % len(scores)]
            return json.dumps({
                "score": chosen_score,
                "reasoning": f"Deterministic mock judge verdict ({digest[:8]}).",
                "confidence": 0.85,
            })
        if behaviour == "always_fail":
            return "Incorrect answer: fabricated information that contradicts ground truth."
        context, question = self._split_prompt(prompt)
        q_tokens = _tokens(question)

        if behaviour == "parametric":
            if not context:
                # Passes without context
                return "The expected answer is 30 days according to standard policy."
            # Fails / gets distracted when context is present
            return "Confused by context formatting; unable to answer the question."

        if behaviour == "context_free":
            # Answers correctly whether context is present or not
            return "The expected answer is 30 days according to standard policy."

        if behaviour == "oracle_only":
            # Only answers correctly if gold context is present
            has_gold = "gold" in context.lower() or "oracle" in context.lower()
            if has_gold and context:
                sentences = [s.strip() for s in _SENTENCE_SPLIT.split(context) if s.strip()]
                scored = sorted(
                    sentences,
                    key=lambda s: len(q_tokens & _tokens(s)) / (1 + 0.02 * len(s)),
                    reverse=True,
                )
                return scored[0] if scored else "The expected answer is 30 days according to gold context."
            return "Irrelevant retrieved text: unable to find the correct answer."

        if context:
            sentences = [s.strip() for s in _SENTENCE_SPLIT.split(context) if s.strip()]
            scored = sorted(
                sentences,
                key=lambda s: len(q_tokens & _tokens(s)) / (1 + 0.02 * len(s)),
                reverse=True,
            )
            best = scored[0] if scored else ""
            if behaviour == "verbose" and len(scored) > 1:
                best = " ".join(scored[:2])
            if behaviour == "hallucinate":
                return (
                    "According to internal records updated last quarter, the answer is "
                    "handled by a dedicated escalation team with no published limit."
                )
            return best or "The provided context does not contain that information."
        if behaviour == "hallucinate":
            return "The documented value is 90 days according to the 2023 revision."
        return "No supporting context was provided, so this answer cannot be grounded."

    async def discover_models(self) -> list[ModelInfo]:
        from app.providers.filtering import filter_chat_models

        raw_models = [
            ModelInfo(
                id=f"mock-{b.replace('_', '-')}",
                provider=self.key,
                label=f"mock · {b}",
                description=f"Deterministic '{b}' behaviour for testing the pipeline.",
                context_window=8192,
                source="discovered",
                tier="free",
            )
            for b in self.BEHAVIOURS
        ]
        chat_models, _ = filter_chat_models(raw_models)
        return chat_models

    async def list_models(self) -> list[ModelInfo]:
        return await self.discover_models()
