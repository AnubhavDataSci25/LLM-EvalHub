"""LLM-as-judge evaluators.

Used only for the metrics where a judge genuinely outperforms lexical matching
(correctness, answer relevance, faithfulness). Judge scores are always stored
with `kind="llm_judge"`, the judge model id and the judge's own rationale, so a
reader can tell a judged score from a deterministic one.

If no judge is configured — or the judge call fails — the caller falls back to
the deterministic evaluator and the metric is relabelled accordingly. A judge
failure never invents a score.

LangChain `PromptTemplate` + `JsonOutputParser` provide the prompt/structured
output plumbing; the actual call goes through our own provider abstraction so
judging works across every supported provider.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.evaluation.metrics import MetricOutcome
from app.providers import LLMProvider

logger = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

JUDGE_SYSTEM_PROMPT = (
    "You are a strict, impartial evaluation judge for an LLM benchmarking platform. "
    "You never reward fluency over accuracy. You reply with JSON only — no prose, "
    "no markdown fences."
)

CORRECTNESS_PROMPT = PromptTemplate.from_template(
    """Judge whether the ANSWER is factually correct with respect to the REFERENCE answer.

Scoring guide:
1.0 = fully correct, conveys the same facts as the reference
0.75 = mostly correct, minor omission that does not change the meaning
0.5 = partially correct, missing or muddling an important element
0.25 = mostly incorrect, but touches the right topic
0.0 = incorrect, contradicts the reference, or refuses to answer

QUESTION:
{question}

REFERENCE:
{reference}

ANSWER:
{answer}

Respond with JSON exactly like:
{{"score": 0.0, "reasoning": "one or two sentences", "confidence": 0.0}}"""
)

RELEVANCE_PROMPT = PromptTemplate.from_template(
    """Judge how directly the ANSWER addresses the QUESTION that was asked.
Ignore factual accuracy here — only judge whether it answers *this* question.

1.0 = answers the question directly and completely
0.5 = partially addresses it, or buries the answer in unrelated content
0.0 = does not address the question, is evasive, or is empty

QUESTION:
{question}

ANSWER:
{answer}

Respond with JSON exactly like:
{{"score": 0.0, "reasoning": "one or two sentences", "confidence": 0.0}}"""
)

FAITHFULNESS_PROMPT = PromptTemplate.from_template(
    """Judge whether every claim in the ANSWER is supported by the CONTEXT.
A claim that is true in the world but absent from the context is UNSUPPORTED.

1.0 = every claim is supported by the context
0.5 = some claims supported, at least one unsupported
0.0 = the central claim is unsupported or contradicts the context

CONTEXT:
{context}

ANSWER:
{answer}

Respond with JSON exactly like:
{{"score": 0.0, "reasoning": "one or two sentences", "unsupported_claims": ["..."], "confidence": 0.0}}"""
)


@dataclass(slots=True)
class JudgeConfig:
    provider: LLMProvider
    model: str
    temperature: float = 0.0
    max_tokens: int = 400

    @property
    def label(self) -> str:
        return f"{self.provider.key}/{self.model}"


def _coerce_payload(text: str) -> dict[str, Any]:
    """Parse a judge response into a dict, tolerating markdown fences/preambles."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        return JsonOutputParser().parse(cleaned)
    except Exception:
        pass
    match = _JSON_BLOCK.search(cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Judge response was not valid JSON: {cleaned[:200]}")


def _clamp(value: Any, default: float | None = None) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


class LLMJudge:
    """Runs judged metrics through any configured provider."""

    def __init__(self, config: JudgeConfig) -> None:
        self.config = config

    async def _ask(self, prompt: str) -> dict[str, Any]:
        response = await self.config.provider.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            system_prompt=JUDGE_SYSTEM_PROMPT,
        )
        if response.is_empty:
            raise ValueError("Judge returned an empty response.")
        return _coerce_payload(response.text)

    async def _score(self, metric: str, prompt: str) -> MetricOutcome:
        try:
            payload = await self._ask(prompt)
        except ProviderError as exc:
            logger.warning("judge provider error on %s: %s", metric, exc.message)
            return MetricOutcome.unavailable(
                metric, f"Judge unavailable ({exc.kind}).", kind="llm_judge"
            )
        except ValueError as exc:
            logger.warning("judge parse error on %s: %s", metric, exc)
            return MetricOutcome.unavailable(
                metric, "Judge returned an unparseable response.", kind="llm_judge"
            )

        score = _clamp(payload.get("score"))
        if score is None:
            return MetricOutcome.unavailable(
                metric, "Judge omitted a numeric score.", kind="llm_judge"
            )
        evidence = str(payload.get("reasoning") or "").strip()[:800] or None
        unsupported = payload.get("unsupported_claims")
        if isinstance(unsupported, list) and unsupported:
            evidence = f"{evidence or ''} Unsupported: {'; '.join(map(str, unsupported[:3]))}"[:900]
        return MetricOutcome(
            metric=metric,
            kind="llm_judge",
            raw_score=score,
            normalized_score=score,
            confidence=_clamp(payload.get("confidence"), 0.6),
            judge_model=self.config.label,
            evidence=evidence,
        )

    async def correctness(
        self, question: str, answer: str | None, reference: str | None
    ) -> MetricOutcome:
        if not (reference or "").strip():
            return MetricOutcome.unavailable(
                "correctness", "No ground_truth supplied for this test case.", kind="llm_judge"
            )
        return await self._score(
            "correctness",
            CORRECTNESS_PROMPT.format(
                question=question, reference=reference, answer=answer or "(empty)"
            ),
        )

    async def answer_relevance(self, question: str, answer: str | None) -> MetricOutcome:
        return await self._score(
            "answer_relevance",
            RELEVANCE_PROMPT.format(question=question, answer=answer or "(empty)"),
        )

    async def faithfulness(self, answer: str | None, contexts: list[str]) -> MetricOutcome:
        joined = "\n\n".join(c for c in contexts if c)
        if not joined.strip():
            return MetricOutcome.unavailable(
                "faithfulness", "No context available to judge grounding.", kind="llm_judge"
            )
        return await self._score(
            "faithfulness",
            FAITHFULNESS_PROMPT.format(context=joined[:8000], answer=answer or "(empty)"),
        )
