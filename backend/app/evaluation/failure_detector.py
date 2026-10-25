"""Failure classification.

Design rule from the spec: *do not label every low score as hallucination*.
Classification therefore runs as an ordered rule cascade, cheapest and most
certain first:

  1. infrastructure signals (provider error, timeout, empty response),
  2. retrieval signals (context recall/precision) — a retrieval problem is not
     a model problem,
  3. grounding signals (faithfulness) — unsupported claims,
  4. answer-quality signals (correctness, relevance).

Each detection carries the evidence that produced it and a confidence derived
from how far the signal is from its threshold, never a fixed number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.metrics import MetricOutcome, coverage

# Failure taxonomy shown in the UI.
FAILURE_TYPES = {
    "provider_error": "The provider rejected or failed the request.",
    "timeout": "The provider did not respond within the configured timeout.",
    "empty_response": "The model returned no content.",
    "poor_retrieval": "The retriever did not surface the evidence needed to answer.",
    "missing_information": "The answer omits information that the expected answer contains.",
    "unsupported_claim": "Part of the answer is not supported by the retrieved context.",
    "hallucination": "The answer asserts specifics that contradict or are absent from the context.",
    "incorrect_answer": "The answer disagrees with the expected answer.",
    "low_relevance": "The answer does not address the question that was asked.",
    "high_latency": "The answer was acceptable but far slower than the configured budget.",
}

SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}


@dataclass(slots=True)
class FailureThresholds:
    correctness: float = 0.5
    faithfulness: float = 0.6
    answer_relevance: float = 0.5
    context_precision: float = 0.3
    context_recall: float = 0.5
    latency_ms: float = 15000.0

    def as_dict(self) -> dict[str, float]:
        return {
            "correctness": self.correctness,
            "faithfulness": self.faithfulness,
            "answer_relevance": self.answer_relevance,
            "context_precision": self.context_precision,
            "context_recall": self.context_recall,
            "latency_ms": self.latency_ms,
        }


@dataclass(slots=True)
class FailureVerdict:
    failed: bool
    failure_type: str | None = None
    severity: str = "medium"
    detector: str = "rule"
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)


def _confidence(value: float, threshold: float, *, floor: float = 0.55) -> float:
    """Confidence grows with distance below the threshold. Never reported as 1.0."""
    if threshold <= 0:
        return floor
    gap = max(0.0, (threshold - value) / threshold)
    return round(min(0.95, floor + gap * 0.4), 2)


def classify(
    *,
    answer: str | None,
    ground_truth: str | None,
    contexts: list[str],
    outcomes: list[MetricOutcome],
    latency_ms: float | None,
    error_kind: str | None = None,
    error_message: str | None = None,
    thresholds: FailureThresholds | None = None,
) -> FailureVerdict:
    th = thresholds or FailureThresholds()
    scores = {
        o.metric: o.normalized_score
        for o in outcomes
        if o.available and o.normalized_score is not None
    }
    signals: dict[str, Any] = {
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "thresholds": th.as_dict(),
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        "has_context": bool([c for c in contexts if (c or "").strip()]),
    }

    # -- 1. infrastructure ------------------------------------------------
    if error_kind:
        failure_type = "timeout" if error_kind == "timeout" else "provider_error"
        return FailureVerdict(
            failed=True,
            failure_type=failure_type,
            severity="critical",
            detector="provider",
            confidence=0.98,
            evidence=[error_message or f"Provider reported '{error_kind}'."],
            signals=signals,
        )

    if not (answer or "").strip():
        return FailureVerdict(
            failed=True,
            failure_type="empty_response",
            severity="critical",
            detector="rule",
            confidence=0.98,
            evidence=["The model produced no text for this test case."],
            signals=signals,
        )

    evidence: list[str] = []

    # -- 2. retrieval -----------------------------------------------------
    recall = scores.get("context_recall")
    precision = scores.get("context_precision")
    if recall is not None and recall < th.context_recall:
        evidence.append(
            f"Context recall {recall:.2f} is below the {th.context_recall:.2f} threshold — "
            "the expected answer is largely absent from the retrieved context."
        )
        if precision is not None:
            evidence.append(f"Context precision was {precision:.2f}.")
        return FailureVerdict(
            failed=True,
            failure_type="poor_retrieval",
            severity="high",
            detector="metric",
            confidence=_confidence(recall, th.context_recall),
            evidence=evidence,
            signals=signals,
        )
    if precision is not None and precision < th.context_precision and signals["has_context"]:
        evidence.append(
            f"Context precision {precision:.2f} is below the {th.context_precision:.2f} "
            "threshold — most retrieved chunks are noise."
        )
        return FailureVerdict(
            failed=True,
            failure_type="poor_retrieval",
            severity="medium",
            detector="metric",
            confidence=_confidence(precision, th.context_precision),
            evidence=evidence,
            signals=signals,
        )

    # -- 3. grounding -----------------------------------------------------
    faith = scores.get("faithfulness")
    correctness = scores.get("correctness")
    if faith is not None and faith < th.faithfulness:
        contradicts = (
            correctness is not None and correctness < th.correctness and bool(ground_truth)
        )
        failure_type = "hallucination" if contradicts and faith < 0.35 else "unsupported_claim"
        evidence.append(
            f"Faithfulness {faith:.2f} is below the {th.faithfulness:.2f} threshold — "
            "at least one claim is not supported by the retrieved context."
        )
        if contradicts:
            evidence.append(
                f"Correctness {correctness:.2f} also disagrees with the expected answer, so "
                "the unsupported content is likely fabricated rather than merely uncited."
            )
        return FailureVerdict(
            failed=True,
            failure_type=failure_type,
            severity="high",
            detector="metric",
            confidence=_confidence(faith, th.faithfulness),
            evidence=evidence,
            signals=signals,
        )

    # -- 4. answer quality ------------------------------------------------
    if correctness is not None and correctness < th.correctness:
        covered = coverage(ground_truth, answer)
        failure_type = "missing_information" if covered >= 0.4 else "incorrect_answer"
        evidence.append(
            f"Correctness {correctness:.2f} is below the {th.correctness:.2f} threshold."
        )
        evidence.append(
            f"The answer covers {covered:.0%} of the expected answer's content words."
        )
        return FailureVerdict(
            failed=True,
            failure_type=failure_type,
            severity="high" if failure_type == "incorrect_answer" else "medium",
            detector="metric",
            confidence=_confidence(correctness, th.correctness),
            evidence=evidence,
            signals=signals,
        )

    relevance = scores.get("answer_relevance")
    if relevance is not None and relevance < th.answer_relevance:
        evidence.append(
            f"Answer relevance {relevance:.2f} is below the {th.answer_relevance:.2f} "
            "threshold — the response does not address the question directly."
        )
        return FailureVerdict(
            failed=True,
            failure_type="low_relevance",
            severity="medium",
            detector="metric",
            confidence=_confidence(relevance, th.answer_relevance),
            evidence=evidence,
            signals=signals,
        )

    # -- 5. performance-only failure --------------------------------------
    if latency_ms is not None and latency_ms > th.latency_ms:
        return FailureVerdict(
            failed=True,
            failure_type="high_latency",
            severity="low",
            detector="rule",
            confidence=0.9,
            evidence=[
                f"Latency {latency_ms:.0f} ms exceeded the {th.latency_ms:.0f} ms budget, "
                "even though answer quality was acceptable."
            ],
            signals=signals,
        )

    return FailureVerdict(failed=False, signals=signals)
