"""Typed state for the LangGraph evaluation workflow."""

from __future__ import annotations

from typing import Any, TypedDict

from app.evaluation.metrics import MetricOutcome


class EvaluationState(TypedDict, total=False):
    """State threaded through the evaluation graph for a single work unit.

    A *work unit* is one test case evaluated against one model. Running the
    graph per unit (rather than per run) keeps the conditional branches simple,
    makes partial persistence natural, and means a single provider failure never
    aborts the whole experiment.
    """

    # identity
    run_id: str
    experiment_id: str
    dataset_id: str
    test_case_id: str
    provider: str
    model: str
    model_label: str | None

    # inputs
    question: str
    ground_truth: str | None
    inline_context: str | None
    system_prompt: str | None
    prompt_template: str
    temperature: float
    max_tokens: int

    # retrieval
    rag_enabled: bool
    collection: str | None
    retriever_strategy: str
    top_k: int
    retrieved_context: list[str]
    retrieval_meta: dict[str, Any]

    # generation
    rendered_prompt: str
    generated_answer: str | None
    latency_ms: float | None
    usage: dict[str, Any]
    finish_reason: str | None
    resolved_model: str | None
    error_kind: str | None
    error_message: str | None

    # evaluation
    metric_outcomes: list[MetricOutcome]
    metric_scores: dict[str, float | None]
    composite_score: float | None
    composite_breakdown: dict[str, Any]

    # failure analysis
    passed: bool | None
    failure: dict[str, Any] | None

    # bookkeeping
    status: str
    stage: str
    persisted: bool
    warnings: list[str]
