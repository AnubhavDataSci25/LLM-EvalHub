"""The LangGraph evaluation workflow.

    START
      ↓
    prepare            resolve provider/model, render the prompt
      ↓
    (rag_enabled?) ──no──┐
      ↓ yes              │
    retrieve             │
      ↓                  │
    generate  ←──────────┘
      ↓
    evaluate           run the selected metrics
      ↓
    detect_failure     rule cascade over the metric evidence
      ↓
    persist            write the result through an injected callback
      ↓
    END

LangGraph is used here for controlled, inspectable workflow orchestration — not
because the problem needs agents. The conditional edge on `rag_enabled` is the
only branch, which is exactly the amount of control flow this pipeline has.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.core.concurrency import with_retries
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.evaluation.aggregators import composite_score
from app.evaluation.failure_detector import FailureThresholds, classify
from app.evaluation.registry import EvaluationInputs, Evaluator
from app.providers.base import LLMProvider
from app.services.experiment_service import render_prompt
from app.workflows.state import EvaluationState

logger = get_logger(__name__)

RetrieverFactory = Callable[[str, str, int], Awaitable[Any]]
PersistCallback = Callable[[EvaluationState], Awaitable[None]]


class EvaluationGraph:
    """Builds and runs the compiled evaluation graph."""

    def __init__(
        self,
        *,
        providers: dict[str, LLMProvider],
        evaluator: Evaluator,
        retriever_factory: RetrieverFactory | None = None,
        persist: PersistCallback | None = None,
        thresholds: FailureThresholds | None = None,
        weights: dict[str, float] | None = None,
        latency_budget_ms: float = 4000.0,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.providers = providers
        self.evaluator = evaluator
        self.retriever_factory = retriever_factory
        self.persist_callback = persist
        self.thresholds = thresholds or FailureThresholds()
        self.weights = weights
        self.latency_budget_ms = latency_budget_ms
        self.timeout_seconds = timeout_seconds
        self._persist_lock = asyncio.Lock()
        self.graph = self._build()

    # -- graph construction ----------------------------------------------
    def _build(self):
        builder: StateGraph = StateGraph(EvaluationState)
        builder.add_node("prepare", self.prepare)
        builder.add_node("retrieve", self.retrieve)
        builder.add_node("generate", self.generate)
        builder.add_node("evaluate", self.evaluate)
        builder.add_node("detect_failure", self.detect_failure)
        builder.add_node("persist", self.persist)

        builder.add_edge(START, "prepare")
        builder.add_conditional_edges(
            "prepare",
            self.route_retrieval,
            {"retrieve": "retrieve", "generate": "generate"},
        )
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", "evaluate")
        builder.add_edge("evaluate", "detect_failure")
        builder.add_edge("detect_failure", "persist")
        builder.add_edge("persist", END)
        return builder.compile()

    async def run(self, state: EvaluationState) -> EvaluationState:
        return await self.graph.ainvoke(state)  # type: ignore[return-value]

    # -- nodes -------------------------------------------------------------
    @staticmethod
    def route_retrieval(state: EvaluationState) -> str:
        return "retrieve" if state.get("rag_enabled") and state.get("collection") else "generate"

    async def prepare(self, state: EvaluationState) -> dict[str, Any]:
        return {
            "stage": "prepare",
            "status": "running",
            "retrieved_context": [],
            "retrieval_meta": {},
            "warnings": list(state.get("warnings") or []),
        }

    async def retrieve(self, state: EvaluationState) -> dict[str, Any]:
        if self.retriever_factory is None:
            return {
                "stage": "retrieve",
                "warnings": [*state.get("warnings", []), "No retriever available; skipped retrieval."],
            }
        try:
            retriever = await self.retriever_factory(
                state["collection"] or "default",
                state.get("retriever_strategy", "vector"),
                int(state.get("top_k", 4)),
            )
            result = await retriever.retrieve(state["question"], state.get("top_k", 4))
            return {
                "stage": "retrieve",
                "retrieved_context": result.contexts,
                "retrieval_meta": result.as_dict(),
            }
        except Exception as exc:  # retrieval failure must not abort the unit
            logger.warning("retrieval failed for case %s: %s", state.get("test_case_id"), exc)
            return {
                "stage": "retrieve",
                "retrieved_context": [],
                "retrieval_meta": {"error": str(exc)[:300]},
                "warnings": [*state.get("warnings", []), f"Retrieval failed: {exc}"],
            }

    async def generate(self, state: EvaluationState) -> dict[str, Any]:
        contexts = list(state.get("retrieved_context") or [])
        if not contexts and state.get("inline_context"):
            contexts = [state["inline_context"]]  # dataset-supplied context

        prompt = render_prompt(
            state.get("prompt_template", ""),
            question=state["question"],
            context="\n\n".join(contexts),
        )
        provider = self.providers.get(state["provider"])
        if provider is None:
            return {
                "stage": "generate",
                "status": "error",
                "rendered_prompt": prompt,
                "retrieved_context": contexts,
                "error_kind": "provider_not_configured",
                "error_message": f"Provider '{state['provider']}' is unavailable.",
                "generated_answer": None,
                "latency_ms": None,
            }

        async def _call():
            return await provider.generate(
                prompt=prompt,
                model=state["model"],
                temperature=float(state.get("temperature", 0.0)),
                max_tokens=int(state.get("max_tokens", 512)),
                system_prompt=state.get("system_prompt"),
                timeout=self.timeout_seconds,
            )

        try:
            response = await with_retries(_call)
        except ProviderError as exc:
            logger.info(
                "provider error on %s/%s: %s", state["provider"], state["model"], exc.kind
            )
            return {
                "stage": "generate",
                "status": "error",
                "rendered_prompt": prompt,
                "retrieved_context": contexts,
                "error_kind": exc.kind,
                "error_message": exc.message,
                "generated_answer": None,
                "latency_ms": None,
            }
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("unexpected generation error")
            return {
                "stage": "generate",
                "status": "error",
                "rendered_prompt": prompt,
                "retrieved_context": contexts,
                "error_kind": "unexpected_error",
                "error_message": str(exc)[:500],
                "generated_answer": None,
                "latency_ms": None,
            }

        return {
            "stage": "generate",
            "status": "completed",
            "rendered_prompt": prompt,
            "retrieved_context": contexts,
            "generated_answer": response.text,
            "latency_ms": response.latency_ms,
            "usage": response.usage,
            "finish_reason": response.finish_reason,
            "resolved_model": response.resolved_model,
            "error_kind": None,
            "error_message": None,
        }

    async def evaluate(self, state: EvaluationState) -> dict[str, Any]:
        if state.get("status") == "error":
            # No answer means no scoreable metrics. We record latency only if it
            # exists, and never invent zeros for the quality metrics.
            return {
                "stage": "evaluate",
                "metric_outcomes": [],
                "metric_scores": {},
                "composite_score": None,
                "composite_breakdown": {},
            }

        outcomes = await self.evaluator.evaluate(
            EvaluationInputs(
                question=state["question"],
                answer=state.get("generated_answer"),
                ground_truth=state.get("ground_truth"),
                contexts=list(state.get("retrieved_context") or []),
                latency_ms=state.get("latency_ms"),
                latency_budget_ms=self.latency_budget_ms,
            )
        )
        scores = {
            o.metric: o.normalized_score
            for o in outcomes
            if o.available and o.normalized_score is not None
        }
        composite, breakdown = composite_score(scores, self.weights)
        return {
            "stage": "evaluate",
            "metric_outcomes": outcomes,
            "metric_scores": scores,
            "composite_score": composite,
            "composite_breakdown": breakdown,
        }

    async def detect_failure(self, state: EvaluationState) -> dict[str, Any]:
        verdict = classify(
            answer=state.get("generated_answer"),
            ground_truth=state.get("ground_truth"),
            contexts=list(state.get("retrieved_context") or []),
            outcomes=list(state.get("metric_outcomes") or []),
            latency_ms=state.get("latency_ms"),
            error_kind=state.get("error_kind"),
            error_message=state.get("error_message"),
            thresholds=self.thresholds,
        )
        failure = None
        if verdict.failed:
            failure = {
                "failure_type": verdict.failure_type,
                "severity": verdict.severity,
                "detector": verdict.detector,
                "confidence": verdict.confidence,
                "evidence": verdict.evidence,
                "signals": verdict.signals,
            }
        return {"stage": "detect_failure", "passed": not verdict.failed, "failure": failure}

    async def persist(self, state: EvaluationState) -> dict[str, Any]:
        if self.persist_callback is None:
            return {"stage": "persist", "persisted": False}
        # Database writes are serialised: the graph runs many units concurrently
        # but a SQLAlchemy Session is not safe for concurrent use.
        async with self._persist_lock:
            await self.persist_callback(state)
        return {"stage": "persist", "persisted": True}
