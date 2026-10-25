"""Metric registry + the evaluator that scores a single result.

The registry is the single source of truth for: what a metric means, what
inputs it needs, whether it is deterministic or judged, and whether a higher
value is better. The frontend renders metric documentation directly from it, so
the UI can never drift from the implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation import metrics as det
from app.evaluation.judge import LLMJudge
from app.evaluation.metrics import MetricOutcome

DETERMINISTIC = "deterministic"
LLM_JUDGE = "llm_judge"
PERFORMANCE = "performance"
RAGAS = "ragas"


@dataclass(slots=True)
class MetricSpec:
    key: str
    label: str
    description: str
    default_kind: str
    requires: list[str] = field(default_factory=list)
    judge_capable: bool = False
    higher_is_better: bool = True
    default_enabled: bool = True
    group: str = "quality"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "default_kind": self.default_kind,
            "requires": self.requires,
            "judge_capable": self.judge_capable,
            "higher_is_better": self.higher_is_better,
            "default_enabled": self.default_enabled,
            "group": self.group,
        }


METRIC_SPECS: dict[str, MetricSpec] = {
    "correctness": MetricSpec(
        key="correctness",
        label="Correctness",
        description=(
            "Does the answer match the expected answer? Judged by an LLM when a judge "
            "model is configured, otherwise scored deterministically with token-F1, "
            "cosine similarity and ground-truth coverage."
        ),
        default_kind=DETERMINISTIC,
        requires=["ground_truth"],
        judge_capable=True,
    ),
    "answer_relevance": MetricSpec(
        key="answer_relevance",
        label="Answer relevance",
        description=(
            "Does the answer actually address the question asked, regardless of whether "
            "it is factually right?"
        ),
        default_kind=DETERMINISTIC,
        requires=["question"],
        judge_capable=True,
    ),
    "faithfulness": MetricSpec(
        key="faithfulness",
        label="Faithfulness",
        description=(
            "Is every claim in the answer supported by the retrieved context? A claim "
            "that is true in the world but absent from the context counts as unsupported."
        ),
        default_kind=DETERMINISTIC,
        requires=["context"],
        judge_capable=True,
    ),
    "context_precision": MetricSpec(
        key="context_precision",
        label="Context precision",
        description=(
            "Rank-weighted share of retrieved chunks that are actually relevant. Low "
            "values mean the retriever is returning noise."
        ),
        default_kind=DETERMINISTIC,
        requires=["context"],
        group="retrieval",
    ),
    "context_recall": MetricSpec(
        key="context_recall",
        label="Context recall",
        description=(
            "How much of the expected answer is present in the retrieved context. Low "
            "values mean the retriever missed the evidence entirely."
        ),
        default_kind=DETERMINISTIC,
        requires=["context", "ground_truth"],
        group="retrieval",
    ),
    "retrieval_hit_rate": MetricSpec(
        key="retrieval_hit_rate",
        label="Retrieval hit rate",
        description="Did retrieval surface at least one chunk covering the expected answer?",
        default_kind=DETERMINISTIC,
        requires=["context", "ground_truth"],
        default_enabled=False,
        group="retrieval",
    ),
    "latency": MetricSpec(
        key="latency",
        label="Latency",
        description=(
            "Wall-clock time for the generation call, normalised against a configurable "
            "budget so it can be weighted alongside quality metrics."
        ),
        default_kind=PERFORMANCE,
        requires=[],
        higher_is_better=False,
        group="performance",
    ),
    "response_length": MetricSpec(
        key="response_length",
        label="Response length",
        description="Word count of the generated answer. Informational — never a pass/fail signal.",
        default_kind=PERFORMANCE,
        requires=[],
        default_enabled=False,
        group="performance",
    ),
}

DEFAULT_METRICS = [k for k, s in METRIC_SPECS.items() if s.default_enabled]
RAG_METRICS = ["context_precision", "context_recall", "retrieval_hit_rate"]


def metric_spec(key: str) -> MetricSpec | None:
    return METRIC_SPECS.get(key)


def validate_metrics(keys: list[str]) -> list[str]:
    """Keep only known metric keys, preserving registry order."""
    requested = {k.strip().lower() for k in keys if k}
    return [k for k in METRIC_SPECS if k in requested]


@dataclass(slots=True)
class EvaluationInputs:
    question: str
    answer: str | None
    ground_truth: str | None
    contexts: list[str]
    latency_ms: float | None
    latency_budget_ms: float = 4000.0


class Evaluator:
    """Scores one result across the requested metrics.

    Judge usage policy: a judge is used only for `judge_capable` metrics and only
    when one is configured. Everything else stays deterministic, which keeps
    evaluation cheap and reproducible.
    """

    def __init__(
        self,
        metrics: list[str],
        *,
        judge: LLMJudge | None = None,
        ragas_adapter: Any | None = None,
    ) -> None:
        self.metrics = validate_metrics(metrics) or list(DEFAULT_METRICS)
        self.judge = judge
        self.ragas = ragas_adapter

    async def evaluate(self, inputs: EvaluationInputs) -> list[MetricOutcome]:
        outcomes: list[MetricOutcome] = []
        for key in self.metrics:
            outcome = await self._evaluate_one(key, inputs)
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    async def _evaluate_one(self, key: str, i: EvaluationInputs) -> MetricOutcome | None:
        if key == "latency":
            return det.latency_metric(i.latency_ms, budget_ms=i.latency_budget_ms)
        if key == "response_length":
            return det.response_length_metric(i.answer)
        if key == "context_precision":
            return await self._maybe_ragas(
                key, i, det.context_precision(i.contexts, i.ground_truth, i.question)
            )
        if key == "context_recall":
            return await self._maybe_ragas(
                key, i, det.context_recall(i.contexts, i.ground_truth)
            )
        if key == "retrieval_hit_rate":
            return det.retrieval_hit_rate(i.contexts, i.ground_truth)

        if key == "correctness":
            fallback = det.correctness_lexical(i.answer, i.ground_truth)
            if self.judge and (i.ground_truth or "").strip() and (i.answer or "").strip():
                judged = await self.judge.correctness(i.question, i.answer, i.ground_truth)
                return judged if judged.available else fallback
            return fallback

        if key == "answer_relevance":
            fallback = det.answer_relevance_lexical(i.answer, i.question)
            if self.judge and (i.answer or "").strip():
                judged = await self.judge.answer_relevance(i.question, i.answer)
                return judged if judged.available else fallback
            return fallback

        if key == "faithfulness":
            fallback = det.faithfulness_lexical(i.answer, i.contexts)
            if self.judge and i.contexts and (i.answer or "").strip():
                judged = await self.judge.faithfulness(i.answer, i.contexts)
                return judged if judged.available else fallback
            return fallback
        return None

    async def _maybe_ragas(
        self, key: str, i: EvaluationInputs, fallback: MetricOutcome
    ) -> MetricOutcome:
        if self.ragas is None or not fallback.available:
            return fallback
        result = await self.ragas.score(key, i)
        return result if (result and result.available) else fallback
