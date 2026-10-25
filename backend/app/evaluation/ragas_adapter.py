"""Optional RAGAS integration.

RAGAS is a heavy, optional dependency (`pip install -r requirements-optional.txt`).
When it is installed *and* a judge model is configured, retrieval metrics are
computed with RAGAS's own implementations. When it is not, the deterministic
implementations in `evaluation/metrics.py` are used and every score is labelled
`deterministic` so nothing is misattributed.

This adapter never fabricates a RAGAS score: if the import fails, the wrapper
returns `None` and the caller falls back.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.evaluation.metrics import MetricOutcome

if TYPE_CHECKING:  # pragma: no cover
    from app.evaluation.judge import JudgeConfig
    from app.evaluation.registry import EvaluationInputs

logger = get_logger(__name__)

#: RAGAS metric name -> our metric key
SUPPORTED = {
    "context_precision": "LLMContextPrecisionWithReference",
    "context_recall": "LLMContextRecall",
    "faithfulness": "Faithfulness",
}


def ragas_available() -> bool:
    try:  # pragma: no cover - depends on optional install
        import ragas  # noqa: F401

        return True
    except Exception:
        return False


class RagasAdapter:
    """Thin wrapper around RAGAS single-turn metrics."""

    def __init__(self, judge_config: JudgeConfig | None) -> None:
        self.judge_config = judge_config
        self._llm: Any | None = None
        self._enabled = ragas_available() and judge_config is not None
        if not self._enabled:
            logger.info(
                "RAGAS adapter disabled (installed=%s, judge=%s) — using deterministic metrics.",
                ragas_available(),
                judge_config is not None,
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _build_llm(self) -> Any | None:  # pragma: no cover - optional path
        """Bridge our provider abstraction into a RAGAS-compatible LLM wrapper."""
        if self._llm is not None or not self.judge_config:
            return self._llm
        try:
            from langchain_core.language_models import BaseChatModel  # noqa: F401
            from ragas.llms import LangchainLLMWrapper

            from app.evaluation.langchain_bridge import EvalHubChatModel

            self._llm = LangchainLLMWrapper(
                EvalHubChatModel(
                    provider=self.judge_config.provider,
                    model_name=self.judge_config.model,
                    temperature=self.judge_config.temperature,
                )
            )
        except Exception as exc:
            logger.warning("could not build RAGAS LLM wrapper: %s", exc)
            self._enabled = False
            self._llm = None
        return self._llm

    async def score(self, metric_key: str, inputs: EvaluationInputs) -> MetricOutcome | None:
        if not self._enabled or metric_key not in SUPPORTED:
            return None
        llm = self._build_llm()
        if llm is None:
            return None
        try:  # pragma: no cover - optional path
            import ragas.metrics as ragas_metrics
            from ragas.dataset_schema import SingleTurnSample

            metric_cls = getattr(ragas_metrics, SUPPORTED[metric_key])
            metric = metric_cls(llm=llm)
            sample = SingleTurnSample(
                user_input=inputs.question,
                response=inputs.answer or "",
                retrieved_contexts=list(inputs.contexts),
                reference=inputs.ground_truth or "",
            )
            score = await asyncio.wait_for(metric.single_turn_ascore(sample), timeout=90)
            value = max(0.0, min(1.0, float(score)))
            return MetricOutcome(
                metric=metric_key,
                kind="ragas",
                raw_score=value,
                normalized_score=value,
                judge_model=self.judge_config.label if self.judge_config else None,
                evidence=f"Computed by RAGAS {SUPPORTED[metric_key]}.",
            )
        except Exception as exc:
            logger.warning("RAGAS scoring failed for %s: %s", metric_key, exc)
            return None


def build_ragas_adapter(judge_config: JudgeConfig | None, enabled: bool) -> RagasAdapter | None:
    if not enabled:
        return None
    adapter = RagasAdapter(judge_config)
    return adapter if adapter.enabled else None
