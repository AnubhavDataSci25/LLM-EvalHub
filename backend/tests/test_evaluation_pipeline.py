"""Deterministic pipeline regression: dataset -> provider -> evaluator -> storage.

Re-running this suite must produce identical scores. That property is what makes
the platform usable for regression testing at all, so it is asserted directly.
"""

from __future__ import annotations

import pytest

from app.evaluation.aggregators import composite_score, normalise_weights, summarise_results
from app.evaluation.registry import EvaluationInputs, Evaluator
from app.providers.mock import MockProvider
from app.services.experiment_service import DEFAULT_PROMPT_TEMPLATE, render_prompt

FIXTURE = [
    {
        "question": "What is the refund window?",
        "ground_truth": "Refunds are available within 30 days.",
        "context": "Refunds are available within 30 days of purchase. Shipping is free over $50.",
    },
    {
        "question": "How long is the warranty?",
        "ground_truth": "The warranty lasts 24 months.",
        "context": "All electronics carry a 24 month warranty against defects.",
    },
]


async def _run_fixture(model: str) -> list[dict]:
    provider = MockProvider()
    evaluator = Evaluator(["correctness", "answer_relevance", "faithfulness", "latency"])
    rows = []
    for case in FIXTURE:
        prompt = render_prompt(
            DEFAULT_PROMPT_TEMPLATE, question=case["question"], context=case["context"]
        )
        response = await provider.generate(prompt, model)
        outcomes = await evaluator.evaluate(
            EvaluationInputs(
                question=case["question"],
                answer=response.text,
                ground_truth=case["ground_truth"],
                contexts=[case["context"]],
                latency_ms=1000.0,  # fixed so the metric is comparable across runs
            )
        )
        rows.append(
            {
                "answer": response.text,
                "scores": {
                    o.metric: o.normalized_score for o in outcomes if o.available
                },
            }
        )
    return rows


@pytest.mark.asyncio
async def test_pipeline_is_reproducible():
    first = await _run_fixture("mock-extractive")
    second = await _run_fixture("mock-extractive")
    assert first == second, "identical inputs must produce identical scores"


@pytest.mark.asyncio
async def test_extractive_baseline_beats_hallucinating_model():
    good = await _run_fixture("mock-extractive")
    bad = await _run_fixture("mock-hallucinate")

    def mean(rows, metric):
        values = [r["scores"][metric] for r in rows if metric in r["scores"]]
        return sum(values) / len(values)

    assert mean(good, "correctness") > mean(bad, "correctness")
    assert mean(good, "faithfulness") > mean(bad, "faithfulness")


@pytest.mark.asyncio
async def test_empty_model_scores_zero_on_quality_not_unavailable():
    rows = await _run_fixture("mock-empty")
    assert all(r["answer"] == "" for r in rows)
    assert all(r["scores"]["correctness"] == 0.0 for r in rows)


def test_composite_score_renormalises_over_available_metrics():
    score, breakdown = composite_score(
        {"correctness": 0.8, "faithfulness": 0.6}, {"correctness": 0.5, "faithfulness": 0.5}
    )
    assert score == pytest.approx(0.7)
    assert breakdown["used"] == {"correctness": 0.8, "faithfulness": 0.6}

    partial, partial_breakdown = composite_score(
        {"correctness": 0.8}, {"correctness": 0.5, "latency": 0.5}
    )
    assert partial == pytest.approx(0.8)  # missing metric does not drag the score to 0.4
    assert partial_breakdown["missing"] == ["latency"]


def test_composite_returns_none_without_any_metric():
    score, _ = composite_score({}, {"correctness": 1.0})
    assert score is None


def test_weights_are_normalised_to_one():
    weights = normalise_weights({"correctness": 2, "latency": 2})
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["correctness"] == pytest.approx(0.5)


def test_summary_counts_reflect_status():
    class FakeMetric:
        metric, kind, available, normalized_score, judge_model = "correctness", "deterministic", True, 0.8, None

    class FakeResult:
        def __init__(self, status, passed, latency, composite):
            self.status, self.passed = status, passed
            self.latency_ms, self.composite_score = latency, composite
            self.metrics = [FakeMetric()]
            self.failure = None
            self.error_kind = None
            self.provider, self.model, self.model_label = "mock", "m", None

    results = [
        FakeResult("completed", True, 100, 0.8),
        FakeResult("completed", False, 200, 0.4),
        FakeResult("error", None, None, None),
    ]
    summary = summarise_results(results, ["correctness"])
    assert summary["total_cases"] == 3
    assert summary["completed_cases"] == 2
    assert summary["error_cases"] == 1
    assert summary["failed_cases"] == 1
    assert summary["avg_latency_ms"] == 150
