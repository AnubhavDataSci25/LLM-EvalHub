"""Deterministic metric behaviour — these must be stable across runs."""

from __future__ import annotations

import pytest

from app.evaluation import metrics as det
from app.evaluation.registry import EvaluationInputs, Evaluator, validate_metrics


def test_exact_match_scores_near_one():
    outcome = det.correctness_lexical(
        "Customers can request a refund within 30 days.",
        "Customers can request a refund within 30 days.",
    )
    assert outcome.available and outcome.normalized_score == pytest.approx(1.0, abs=0.01)


def test_wrong_answer_scores_low():
    outcome = det.correctness_lexical(
        "Shipping is free on orders over fifty dollars.",
        "Customers can request a refund within 30 days.",
    )
    assert outcome.normalized_score < 0.2


def test_correctness_unavailable_without_ground_truth():
    outcome = det.correctness_lexical("Some answer", None)
    assert outcome.available is False
    assert outcome.normalized_score is None  # never a fabricated zero


def test_stemming_matches_singular_and_plural():
    assert det.token_f1("refunds policy", "refund policies") > 0.9


def test_faithfulness_penalises_unsupported_claims():
    supported = det.faithfulness_lexical(
        "Refunds are available within 30 days.",
        ["Refunds are available within 30 days of purchase."],
    )
    unsupported = det.faithfulness_lexical(
        "Refunds take ninety days and require a manager signature.",
        ["Refunds are available within 30 days of purchase."],
    )
    assert supported.normalized_score == 1.0
    assert unsupported.normalized_score < supported.normalized_score


def test_faithfulness_unavailable_without_context():
    assert det.faithfulness_lexical("Anything", []).available is False


def test_context_recall_reflects_coverage():
    high = det.context_recall(["Refunds are available within 30 days."], "refund within 30 days")
    low = det.context_recall(["Shipping is free over fifty dollars."], "refund within 30 days")
    assert high.normalized_score > low.normalized_score


def test_context_precision_drops_with_noise():
    clean = det.context_precision(
        ["Refunds are available within 30 days."], "refund within 30 days", "refund?"
    )
    noisy = det.context_precision(
        [
            "Refunds are available within 30 days.",
            "Our head office is in Bristol.",
            "The cafeteria serves lunch at noon.",
        ],
        "refund within 30 days",
        "refund?",
    )
    assert clean.normalized_score > noisy.normalized_score


def test_latency_normalisation_is_inverted():
    fast = det.latency_metric(200, budget_ms=4000)
    slow = det.latency_metric(3800, budget_ms=4000)
    assert fast.normalized_score > slow.normalized_score
    assert fast.raw_score == 200


def test_latency_unavailable_when_missing():
    assert det.latency_metric(None).available is False


def test_validate_metrics_filters_unknown_keys():
    assert validate_metrics(["correctness", "not_a_metric"]) == ["correctness"]


@pytest.mark.asyncio
async def test_evaluator_runs_without_a_judge():
    evaluator = Evaluator(["correctness", "faithfulness", "latency"])
    outcomes = await evaluator.evaluate(
        EvaluationInputs(
            question="What is the refund window?",
            answer="Refunds are available within 30 days.",
            ground_truth="Customers can request a refund within 30 days.",
            contexts=["Refunds are available within 30 days of purchase."],
            latency_ms=500,
        )
    )
    kinds = {o.metric: o.kind for o in outcomes}
    assert kinds["correctness"] == "deterministic"
    assert kinds["latency"] == "performance"
    assert all(o.normalized_score is not None for o in outcomes if o.available)
