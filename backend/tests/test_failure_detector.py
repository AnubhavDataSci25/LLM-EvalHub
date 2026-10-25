"""Failure classification must be evidence-driven, not 'everything is a hallucination'."""

from __future__ import annotations

from app.evaluation.failure_detector import FailureThresholds, classify
from app.evaluation.metrics import MetricOutcome


def outcome(metric: str, score: float) -> MetricOutcome:
    return MetricOutcome(metric=metric, raw_score=score, normalized_score=score)


def test_good_result_passes():
    verdict = classify(
        answer="Refunds are available within 30 days.",
        ground_truth="Refunds within 30 days.",
        contexts=["Refunds are available within 30 days."],
        outcomes=[outcome("correctness", 0.9), outcome("faithfulness", 0.95), outcome("answer_relevance", 0.9)],
        latency_ms=500,
    )
    assert verdict.failed is False and verdict.failure_type is None


def test_provider_error_wins_over_everything():
    verdict = classify(
        answer=None, ground_truth="x", contexts=[], outcomes=[],
        latency_ms=None, error_kind="rate_limited", error_message="429",
    )
    assert verdict.failure_type == "provider_error"
    assert verdict.severity == "critical" and verdict.detector == "provider"


def test_timeout_is_its_own_category():
    verdict = classify(
        answer=None, ground_truth="x", contexts=[], outcomes=[],
        latency_ms=None, error_kind="timeout", error_message="timed out",
    )
    assert verdict.failure_type == "timeout"


def test_empty_answer_detected_deterministically():
    verdict = classify(
        answer="   ", ground_truth="x", contexts=["ctx"], outcomes=[], latency_ms=100
    )
    assert verdict.failure_type == "empty_response"
    assert verdict.detector == "rule"


def test_low_recall_is_retrieval_not_hallucination():
    verdict = classify(
        answer="A confident but wrong answer.",
        ground_truth="The expected answer.",
        contexts=["Completely unrelated text."],
        outcomes=[outcome("context_recall", 0.1), outcome("correctness", 0.1), outcome("faithfulness", 0.2)],
        latency_ms=500,
    )
    assert verdict.failure_type == "poor_retrieval"
    assert "recall" in " ".join(verdict.evidence).lower()


def test_unsupported_claim_versus_hallucination():
    unsupported = classify(
        answer="Something partly grounded.",
        ground_truth="Something partly grounded.",
        contexts=["Some context."],
        outcomes=[outcome("faithfulness", 0.5), outcome("correctness", 0.8), outcome("context_recall", 0.9)],
        latency_ms=400,
    )
    assert unsupported.failure_type == "unsupported_claim"

    hallucinated = classify(
        answer="Invented specifics not present anywhere.",
        ground_truth="The real answer.",
        contexts=["Some context."],
        outcomes=[outcome("faithfulness", 0.1), outcome("correctness", 0.05), outcome("context_recall", 0.9)],
        latency_ms=400,
    )
    assert hallucinated.failure_type == "hallucination"


def test_partial_answer_is_missing_information():
    verdict = classify(
        answer="Customers can request a refund.",
        ground_truth="Customers can request a refund within 30 days of delivery.",
        contexts=[],
        outcomes=[outcome("correctness", 0.4)],
        latency_ms=300,
    )
    assert verdict.failure_type == "missing_information"


def test_high_latency_only_flags_when_quality_is_fine():
    verdict = classify(
        answer="A good answer.",
        ground_truth="A good answer.",
        contexts=[],
        outcomes=[outcome("correctness", 0.95), outcome("answer_relevance", 0.9)],
        latency_ms=30000,
        thresholds=FailureThresholds(latency_ms=15000),
    )
    assert verdict.failure_type == "high_latency" and verdict.severity == "low"


def test_confidence_scales_with_distance_from_threshold():
    mild = classify(
        answer="x", ground_truth="y", contexts=[],
        outcomes=[outcome("correctness", 0.49)], latency_ms=100,
    )
    severe = classify(
        answer="x", ground_truth="y", contexts=[],
        outcomes=[outcome("correctness", 0.02)], latency_ms=100,
    )
    assert severe.confidence > mild.confidence
    assert severe.confidence <= 0.95  # never absolute certainty
