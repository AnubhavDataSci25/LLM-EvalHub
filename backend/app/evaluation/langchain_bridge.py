"""Expose any LLM-EvalHub provider as a LangChain `BaseChatModel`.

This is what lets LangChain-native components (RAGAS evaluators, chains,
structured-output parsers) run on top of Groq, Gemini, Hugging Face, OpenRouter
or NVIDIA NIM without writing a separate LangChain integration per provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from app.providers.base import LLMProvider


def _flatten(messages: list[BaseMessage]) -> tuple[str | None, str]:
    """Collapse a LangChain message list into (system_prompt, user_prompt)."""
    system_parts: list[str] = []
    body: list[str] = []
    for message in messages:
        content = message.content
        text = content if isinstance(content, str) else str(content)
        if isinstance(message, SystemMessage):
            system_parts.append(text)
        else:
            prefix = {"human": "", "ai": "Assistant: "}.get(message.type, f"{message.type}: ")
            body.append(f"{prefix}{text}")
    return ("\n\n".join(system_parts) or None), "\n\n".join(body)


class EvalHubChatModel(BaseChatModel):
    """LangChain adapter over `LLMProvider`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: LLMProvider
    model_name: str
    temperature: float = 0.0
    max_tokens: int = 1024

    @property
    def _llm_type(self) -> str:  # pragma: no cover - LangChain plumbing
        return f"evalhub-{self.provider.key}"

    @property
    def _identifying_params(self) -> dict[str, Any]:  # pragma: no cover
        return {"provider": self.provider.key, "model": self.model_name}

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_prompt, prompt = _flatten(messages)
        response = await self.provider.generate(
            prompt=prompt,
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            system_prompt=system_prompt,
        )
        message = AIMessage(
            content=response.text,
            response_metadata={
                "provider": response.provider,
                "model": response.resolved_model or response.model,
                "latency_ms": response.latency_ms,
                "usage": response.usage,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return asyncio.run(self._agenerate(messages, stop, None, **kwargs))
