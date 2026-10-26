"""LangGraph workflow for Counterfactual Failure Attribution.

Graph structure:
    START
      ↓
    build_inputs      resolve gold context, empty context, distractors
      ↓
    generate          execute counterfactual generation trials with retries
      ↓
    evaluate          evaluate metrics per condition trial using existing evaluators
      ↓
    attribute         apply attribution rules to determine the empirical verdict
      ↓
    persist           write AttributionRun and AttributionCondition rows
      ↓
    END
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.concurrency import with_retries
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.evaluation.attribution import (
    CONDITION_DISTRACTOR_ONLY,
    CONDITION_NO_CONTEXT,
    CONDITION_ORACLE_CONTEXT,
    CONDITION_ORIGINAL,
    AttributionOutcome,
    ConditionAggregate,
    ConditionExecutionResult,
    aggregate_condition_trials,
    compute_attribution,
)
from app.evaluation.failure_detector import FailureThresholds
from app.evaluation.registry import EvaluationInputs, Evaluator
from app.providers.base import LLMProvider
from app.services.experiment_service import render_prompt

logger = get_logger(__name__)

PersistAttributionCallback = Callable[["AttributionState"], Awaitable[None]]


class ConditionTrialSpec(TypedDict, total=False):
    condition: str
    repeat_index: int
    context_text: str
    rendered_prompt: str
    generated_answer: str | None
    latency_ms: float | None
    error_kind: str | None
    error_message: str | None
    scores: dict[str, float | None]
    passed: bool


class AttributionState(TypedDict, total=False):
    # identification
    failure_id: str
    result_id: str
    experiment_id: str
    run_id: str
    test_case_id: str

    # model & config
    provider: str
    model: str
    prompt_template: str
    system_prompt: str | None
    temperature: float
    max_tokens: int
    selected_metrics: list[str]

    # test case data
    question: str
    ground_truth: str | None
    gold_context: str | None
    has_gold_context: bool
    distractor_context: list[str]

    # original stored result
    original_answer: str | None
    original_context: list[str]
    original_scores: dict[str, float | None]
    original_passed: bool
    original_error: str | None

    # execution parameters
    repeats: int
    include_distractor: bool

    # execution state
    trial_specs: list[ConditionTrialSpec]
    trial_results: list[ConditionExecutionResult]
    condition_aggregates: dict[str, ConditionAggregate]
    attribution_outcome: AttributionOutcome

    # bookkeeping
    status: str
    stage: str
    error: str | None
    warnings: list[str]
    persisted: bool


class AttributionGraph:
    """Builds and compiles the counterfactual attribution workflow graph."""

    def __init__(
        self,
        *,
        providers: dict[str, LLMProvider],
        evaluator: Evaluator,
        persist: PersistAttributionCallback | None = None,
        thresholds: FailureThresholds | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.providers = providers
        self.evaluator = evaluator
        self.persist_callback = persist
        self.thresholds = thresholds or FailureThresholds()
        self.timeout_seconds = timeout_seconds
        self._persist_lock = asyncio.Lock()
        self.graph = self._build()

    def _build(self):
        builder: StateGraph = StateGraph(AttributionState)
        builder.add_node("build_inputs", self.build_inputs)
        builder.add_node("generate", self.generate)
        builder.add_node("evaluate", self.evaluate)
        builder.add_node("attribute", self.attribute)
        builder.add_node("persist", self.persist)

        builder.add_edge(START, "build_inputs")
        builder.add_edge("build_inputs", "generate")
        builder.add_edge("generate", "evaluate")
        builder.add_edge("evaluate", "attribute")
        builder.add_edge("attribute", "persist")
        builder.add_edge("persist", END)
        return builder.compile()

    async def run(self, state: AttributionState) -> AttributionState:
        return await self.graph.ainvoke(state)  # type: ignore[return-value]

    # -- Node 1: build_inputs ----------------------------------------------
    async def build_inputs(self, state: AttributionState) -> dict[str, Any]:
        repeats = max(1, min(5, int(state.get("repeats", 1))))
        template = state.get("prompt_template", "")
        question = state.get("question", "")
        gold_context = state.get("gold_context") or ""
        has_gold = bool(gold_context.strip())

        trial_specs: list[ConditionTrialSpec] = []

        # 1. ORIGINAL condition (trial 0, reusing stored result)
        trial_specs.append(
            ConditionTrialSpec(
                condition=CONDITION_ORIGINAL,
                repeat_index=0,
                context_text="\n\n".join(state.get("original_context") or []),
                rendered_prompt=render_prompt(
                    template,
                    question=question,
                    context="\n\n".join(state.get("original_context") or []),
                ),
                generated_answer=state.get("original_answer"),
                latency_ms=None,
                error_kind=state.get("original_error"),
                error_message=None,
                scores=state.get("original_scores") or {},
                passed=bool(state.get("original_passed")),
            )
        )

        # 2. ORACLE_CONTEXT trials (N repeats)
        if has_gold:
            for r in range(repeats):
                trial_specs.append(
                    ConditionTrialSpec(
                        condition=CONDITION_ORACLE_CONTEXT,
                        repeat_index=r,
                        context_text=gold_context,
                        rendered_prompt=render_prompt(
                            template,
                            question=question,
                            context=gold_context,
                        ),
                    )
                )

        # 3. NO_CONTEXT trials (N repeats)
        for r in range(repeats):
            trial_specs.append(
                ConditionTrialSpec(
                    condition=CONDITION_NO_CONTEXT,
                    repeat_index=r,
                    context_text="",
                    rendered_prompt=render_prompt(
                        template,
                        question=question,
                        context="",
                    ),
                )
            )

        # 4. (Optional) DISTRACTOR_ONLY trials
        if state.get("include_distractor") and state.get("distractor_context"):
            dist_text = "\n\n".join(state["distractor_context"])
            for r in range(repeats):
                trial_specs.append(
                    ConditionTrialSpec(
                        condition=CONDITION_DISTRACTOR_ONLY,
                        repeat_index=r,
                        context_text=dist_text,
                        rendered_prompt=render_prompt(
                            template,
                            question=question,
                            context=dist_text,
                        ),
                    )
                )

        return {
            "stage": "build_inputs",
            "has_gold_context": has_gold,
            "repeats": repeats,
            "trial_specs": trial_specs,
            "warnings": list(state.get("warnings") or []),
        }

    # -- Node 2: generate --------------------------------------------------
    async def generate(self, state: AttributionState) -> dict[str, Any]:
        provider_key = state.get("provider", "mock")
        provider = self.providers.get(provider_key)
        model = state.get("model", "")
        temperature = float(state.get("temperature", 0.0))
        max_tokens = int(state.get("max_tokens", 512))
        system_prompt = state.get("system_prompt")

        specs = list(state.get("trial_specs") or [])

        if not state.get("has_gold_context"):
            # Without gold context, counterfactual runs are skipped
            return {"stage": "generate", "trial_specs": specs}

        for spec in specs:
            # Skip original condition - it already has its generated answer
            if spec["condition"] == CONDITION_ORIGINAL:
                continue

            if provider is None:
                spec["error_kind"] = "provider_not_configured"
                spec["error_message"] = f"Provider '{provider_key}' is unavailable."
                continue

            async def _call(prompt=spec["rendered_prompt"]):
                return await provider.generate(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                    timeout=self.timeout_seconds,
                )

            try:
                response = await with_retries(_call)
                spec["generated_answer"] = response.text
                spec["latency_ms"] = response.latency_ms
                spec["error_kind"] = None
                spec["error_message"] = None
            except ProviderError as exc:
                logger.warning(
                    "provider error in condition %s: %s", spec["condition"], exc.kind
                )
                spec["generated_answer"] = None
                spec["latency_ms"] = None
                spec["error_kind"] = exc.kind
                spec["error_message"] = exc.message
            except Exception as exc:  # defensive
                logger.exception("unexpected error generating condition %s", spec["condition"])
                spec["generated_answer"] = None
                spec["latency_ms"] = None
                spec["error_kind"] = "unexpected_error"
                spec["error_message"] = str(exc)[:400]

        return {"stage": "generate", "trial_specs": specs}

    # -- Node 3: evaluate --------------------------------------------------
    async def evaluate(self, state: AttributionState) -> dict[str, Any]:
        specs = state.get("trial_specs") or []
        question = state.get("question", "")
        ground_truth = state.get("ground_truth")

        trials_by_cond: dict[str, list[ConditionExecutionResult]] = {}
        all_trials: list[ConditionExecutionResult] = []

        for spec in specs:
            cond = spec["condition"]
            r_idx = spec.get("repeat_index", 0)
            answer = spec.get("generated_answer")
            error_kind = spec.get("error_kind")
            error_msg = spec.get("error_message")
            scores = dict(spec.get("scores") or {})

            # Evaluate metrics if not already evaluated (original has stored scores)
            if cond != CONDITION_ORIGINAL and not error_kind and answer:
                contexts = [spec["context_text"]] if spec.get("context_text") else []
                outcomes = await self.evaluator.evaluate(
                    EvaluationInputs(
                        question=question,
                        answer=answer,
                        ground_truth=ground_truth,
                        contexts=contexts,
                        latency_ms=spec.get("latency_ms"),
                    )
                )
                scores = {
                    o.metric: o.normalized_score
                    for o in outcomes
                    if o.available and o.normalized_score is not None
                }
                spec["scores"] = scores

            from app.evaluation.attribution import evaluate_trial_pass

            trial_pass = evaluate_trial_pass(
                scores=scores,
                thresholds=self.thresholds,
                error=error_kind,
                answer=answer,
            )
            spec["passed"] = trial_pass

            trial_obj = ConditionExecutionResult(
                condition=cond,
                repeat_index=r_idx,
                generated_answer=answer,
                scores=scores,
                latency_ms=spec.get("latency_ms"),
                error_kind=error_kind,
                error_message=error_msg,
                passed=trial_pass,
            )
            trials_by_cond.setdefault(cond, []).append(trial_obj)
            all_trials.append(trial_obj)

        # Aggregate trials per condition
        aggregates: dict[str, ConditionAggregate] = {}
        for cond, cond_trials in trials_by_cond.items():
            aggregates[cond] = aggregate_condition_trials(
                cond, cond_trials, thresholds=self.thresholds
            )

        return {
            "stage": "evaluate",
            "trial_results": all_trials,
            "condition_aggregates": aggregates,
        }

    # -- Node 4: attribute -------------------------------------------------
    async def attribute(self, state: AttributionState) -> dict[str, Any]:
        aggregates = state.get("condition_aggregates") or {}
        has_gold = bool(state.get("has_gold_context"))

        orig_agg = aggregates.get(CONDITION_ORIGINAL)
        oracle_agg = aggregates.get(CONDITION_ORACLE_CONTEXT)
        no_ctx_agg = aggregates.get(CONDITION_NO_CONTEXT)

        # Determine condition pass flags
        original_pass = orig_agg.passed if orig_agg else bool(state.get("original_passed"))
        oracle_pass = oracle_agg.passed if oracle_agg else False
        no_context_pass = no_ctx_agg.passed if no_ctx_agg else False

        condition_errors: dict[str, str | None] = {}
        for c_name, agg in aggregates.items():
            if agg.error:
                condition_errors[c_name] = agg.error

        outcome = compute_attribution(
            original_pass=original_pass,
            oracle_pass=oracle_pass,
            no_context_pass=no_context_pass,
            has_gold_context=has_gold,
            condition_errors=condition_errors,
            repeats=int(state.get("repeats", 1)),
            condition_aggregates=aggregates,
            thresholds=self.thresholds,
        )

        return {
            "stage": "attribute",
            "attribution_outcome": outcome,
            "status": "completed",
        }

    # -- Node 5: persist ---------------------------------------------------
    async def persist(self, state: AttributionState) -> dict[str, Any]:
        if self.persist_callback is None:
            return {"stage": "persist", "persisted": False}
        async with self._persist_lock:
            await self.persist_callback(state)
        return {"stage": "persist", "persisted": True}
