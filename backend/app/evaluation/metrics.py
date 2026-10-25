"""Deterministic evaluators.

These metrics are computed from text alone: same inputs always produce the same
score, no LLM call, no cost, no variance. They are the backbone of the
regression-test suite and the fallback when no judge model is configured.

Every score returned here is labelled `kind="deterministic"` so the UI can
distinguish it from an LLM-judged score. Where an input is missing (no ground
truth, no retrieved context) the metric is reported as **unavailable** rather
than silently scored zero — a missing metric is never presented as a bad score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.core.text import (  # re-exported for convenience
    STOPWORDS,
    split_sentences,
    stem,
    token_set,
    tokenize,
)

__all__ = [
    "MetricOutcome",
    "tokenize",
    "token_set",
    "stem",
    "split_sentences",
    "STOPWORDS",
    "token_f1",
    "cosine_similarity",
    "coverage",
    "correctness_lexical",
    "answer_relevance_lexical",
    "faithfulness_lexical",
    "context_precision",
    "context_recall",
    "latency_metric",
    "response_length_metric",
    "retrieval_hit_rate",
]


@dataclass(slots=True)
class MetricOutcome:
    """Result of one evaluator for one test case."""

    metric: str
    kind: str = "deterministic"
    raw_score: float | None = None
    normalized_score: float | None = None
    confidence: float | None = None
    judge_model: str | None = None
    evidence: str | None = None
    available: bool = True
    unavailable_reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unavailable(cls, metric: str, reason: str, kind: str = "deterministic") -> MetricOutcome:
        return cls(
            metric=metric,
            kind=kind,
            available=False,
            unavailable_reason=reason,
            raw_score=None,
            normalized_score=None,
        )


# ---------------------------------------------------------------------------
# primitive similarity helpers
# ---------------------------------------------------------------------------
def token_f1(prediction: str | None, reference: str | None) -> float:
    """Standard QA token-overlap F1 (SQuAD-style, stopwords removed)."""
    pred = tokenize(prediction)
    ref = tokenize(reference)
    if not pred or not ref:
        return 0.0
    pred_counts: dict[str, int] = {}
    for token in pred:
        pred_counts[token] = pred_counts.get(token, 0) + 1
    overlap = 0
    for token in ref:
        if pred_counts.get(token, 0) > 0:
            pred_counts[token] -= 1
            overlap += 1
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def cosine_similarity(a: str | None, b: str | None) -> float:
    """Bag-of-words cosine similarity — cheap, deterministic, no model needed."""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    va: dict[str, int] = {}
    vb: dict[str, int] = {}
    for t in ta:
        va[t] = va.get(t, 0) + 1
    for t in tb:
        vb[t] = vb.get(t, 0) + 1
    common = set(va) & set(vb)
    dot = sum(va[t] * vb[t] for t in common)
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    return dot / (na * nb) if na and nb else 0.0


def coverage(reference: str | None, candidate: str | None) -> float:
    """Fraction of reference content words that appear in the candidate text."""
    ref = token_set(reference)
    cand = token_set(candidate)
    if not ref:
        return 0.0
    return len(ref & cand) / len(ref)


# ---------------------------------------------------------------------------
# metric implementations
# ---------------------------------------------------------------------------
def correctness_lexical(answer: str | None, ground_truth: str | None) -> MetricOutcome:
    if not (ground_truth or "").strip():
        return MetricOutcome.unavailable(
            "correctness", "No ground_truth supplied for this test case."
        )
    if not (answer or "").strip():
        return MetricOutcome(
            metric="correctness",
            raw_score=0.0,
            normalized_score=0.0,
            evidence="Model returned an empty answer.",
        )
    f1 = token_f1(answer, ground_truth)
    cos = cosine_similarity(answer, ground_truth)
    cov = coverage(ground_truth, answer)
    # blend: F1 rewards exactness, coverage rewards containing the full answer
    score = round(0.5 * f1 + 0.2 * cos + 0.3 * cov, 4)
    return MetricOutcome(
        metric="correctness",
        raw_score=score,
        normalized_score=score,
        evidence=(
            f"Lexical agreement with ground truth: token-F1={f1:.2f}, "
            f"cosine={cos:.2f}, ground-truth coverage={cov:.2f}."
        ),
        details={"token_f1": round(f1, 4), "cosine": round(cos, 4), "coverage": round(cov, 4)},
    )


def answer_relevance_lexical(answer: str | None, question: str | None) -> MetricOutcome:
    if not (answer or "").strip():
        return MetricOutcome(
            metric="answer_relevance",
            raw_score=0.0,
            normalized_score=0.0,
            evidence="Empty answer cannot be relevant to the question.",
        )
    overlap = coverage(question, answer)
    cos = cosine_similarity(answer, question)
    # A relevant answer addresses the question's content words without merely
    # restating them, so we combine overlap with a mild length sanity check.
    length_penalty = 1.0 if len(tokenize(answer)) >= 3 else 0.5
    score = round(min(1.0, (0.6 * overlap + 0.4 * cos) * 1.4) * length_penalty, 4)
    return MetricOutcome(
        metric="answer_relevance",
        raw_score=score,
        normalized_score=score,
        evidence=f"Question-term overlap={overlap:.2f}, cosine={cos:.2f} (lexical proxy).",
        details={"overlap": round(overlap, 4), "cosine": round(cos, 4)},
    )


def faithfulness_lexical(answer: str | None, contexts: list[str]) -> MetricOutcome:
    """Fraction of answer sentences that are lexically supported by the context.

    This is a *proxy* for the LLM-judged faithfulness metric and is labelled as
    such everywhere it surfaces.
    """
    joined = "\n".join(c for c in contexts if c)
    if not joined.strip():
        return MetricOutcome.unavailable(
            "faithfulness", "No context available — faithfulness requires grounding text."
        )
    if not (answer or "").strip():
        return MetricOutcome(
            metric="faithfulness",
            raw_score=0.0,
            normalized_score=0.0,
            evidence="Empty answer contains no grounded claims.",
        )
    sentences = split_sentences(answer) or [answer or ""]
    context_tokens = token_set(joined)
    supported, unsupported = 0, []
    for sentence in sentences:
        tokens = token_set(sentence)
        if not tokens:
            continue
        support = len(tokens & context_tokens) / len(tokens)
        if support >= 0.6:
            supported += 1
        else:
            unsupported.append(sentence[:160])
    considered = supported + len(unsupported)
    if considered == 0:
        return MetricOutcome.unavailable(
            "faithfulness", "Answer contained no scoreable content words."
        )
    score = round(supported / considered, 4)
    evidence = f"{supported}/{considered} answer sentences lexically supported by context."
    if unsupported:
        evidence += f" Unsupported example: “{unsupported[0]}”"
    return MetricOutcome(
        metric="faithfulness",
        raw_score=score,
        normalized_score=score,
        evidence=evidence,
        details={"supported": supported, "total": considered, "unsupported": unsupported[:3]},
    )


def context_precision(contexts: list[str], reference: str | None, question: str | None) -> MetricOutcome:
    """Share of retrieved chunks that are actually relevant to the expected answer."""
    chunks = [c for c in contexts if (c or "").strip()]
    if not chunks:
        return MetricOutcome.unavailable(
            "context_precision", "No retrieved context — enable RAG or supply context."
        )
    target = (reference or "").strip() or (question or "").strip()
    if not target:
        return MetricOutcome.unavailable(
            "context_precision", "Needs ground_truth or question to judge chunk relevance."
        )
    relevances = [max(coverage(target, c), cosine_similarity(target, c)) for c in chunks]
    relevant_flags = [r >= 0.25 for r in relevances]
    hits = sum(relevant_flags)
    if hits == 0:
        score = 0.0
    else:
        # rank-aware precision@k: earlier relevant chunks are worth more
        running, total = 0, 0.0
        for idx, flag in enumerate(relevant_flags, start=1):
            if flag:
                running += 1
                total += running / idx
        score = total / hits
    score = round(min(1.0, score * (hits / len(chunks)) ** 0.5), 4)
    return MetricOutcome(
        metric="context_precision",
        raw_score=score,
        normalized_score=score,
        evidence=f"{hits}/{len(chunks)} retrieved chunks were relevant (rank-weighted).",
        details={
            "relevant_chunks": hits,
            "total_chunks": len(chunks),
            "per_chunk_relevance": [round(r, 3) for r in relevances],
        },
    )


def context_recall(contexts: list[str], ground_truth: str | None) -> MetricOutcome:
    """How much of the expected answer is actually present in retrieved context."""
    chunks = [c for c in contexts if (c or "").strip()]
    if not chunks:
        return MetricOutcome.unavailable(
            "context_recall", "No retrieved context — enable RAG or supply context."
        )
    if not (ground_truth or "").strip():
        return MetricOutcome.unavailable(
            "context_recall", "No ground_truth supplied for this test case."
        )
    joined = "\n".join(chunks)
    score = round(coverage(ground_truth, joined), 4)
    return MetricOutcome(
        metric="context_recall",
        raw_score=score,
        normalized_score=score,
        evidence=f"{score:.0%} of ground-truth content words are present in retrieved context.",
        details={"chunks": len(chunks)},
    )


def latency_metric(latency_ms: float | None, budget_ms: float = 4000.0) -> MetricOutcome:
    if latency_ms is None:
        return MetricOutcome.unavailable(
            "latency", "No latency recorded (request never completed).", kind="performance"
        )
    normalized = round(max(0.0, min(1.0, 1.0 - (latency_ms / budget_ms))), 4)
    return MetricOutcome(
        metric="latency",
        kind="performance",
        raw_score=round(latency_ms, 2),
        normalized_score=normalized,
        evidence=f"{latency_ms:.0f} ms measured against a {budget_ms:.0f} ms budget.",
        details={"latency_ms": round(latency_ms, 2), "budget_ms": budget_ms},
    )


def response_length_metric(answer: str | None) -> MetricOutcome:
    words = len(tokenize(answer, drop_stopwords=False))
    return MetricOutcome(
        metric="response_length",
        kind="performance",
        raw_score=float(words),
        normalized_score=None,
        evidence=f"{words} words generated.",
        details={"words": words, "characters": len(answer or "")},
    )


def retrieval_hit_rate(contexts: list[str], ground_truth: str | None) -> MetricOutcome:
    """Binary: did retrieval surface *any* chunk that supports the expected answer?"""
    chunks = [c for c in contexts if (c or "").strip()]
    if not chunks:
        return MetricOutcome.unavailable("retrieval_hit_rate", "No retrieved context.")
    if not (ground_truth or "").strip():
        return MetricOutcome.unavailable("retrieval_hit_rate", "No ground_truth supplied.")
    hit = any(coverage(ground_truth, c) >= 0.5 for c in chunks)
    return MetricOutcome(
        metric="retrieval_hit_rate",
        raw_score=1.0 if hit else 0.0,
        normalized_score=1.0 if hit else 0.0,
        evidence="A retrieved chunk covers the expected answer."
        if hit
        else "No retrieved chunk covered the expected answer.",
    )
