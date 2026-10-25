"""Aggregation of per-case results into per-model and per-run summaries.

Aggregates only over cases where a metric was actually available, and always
reports the sample size alongside the mean, so a metric scored on 3 of 50 cases
can never masquerade as a full result.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from typing import Any

from app.evaluation.registry import METRIC_SPECS

#: Default composite weights. Visible and overridable per experiment.
DEFAULT_WEIGHTS: dict[str, float] = {
    "correctness": 0.35,
    "faithfulness": 0.30,
    "answer_relevance": 0.20,
    "latency": 0.15,
}


def normalise_weights(weights: dict[str, float] | None) -> dict[str, float]:
    weights = {k: float(v) for k, v in (weights or DEFAULT_WEIGHTS).items() if float(v) > 0}
    if not weights:
        return dict(DEFAULT_WEIGHTS)
    total = sum(weights.values())
    return {k: round(v / total, 6) for k, v in weights.items()}


def composite_score(
    metric_scores: dict[str, float | None], weights: dict[str, float] | None = None
) -> tuple[float | None, dict[str, Any]]:
    """Weighted composite over the metrics that are actually present.

    Weights are renormalised across available metrics, and the breakdown is
    returned so the UI can show exactly how the number was produced.
    """
    weights = normalise_weights(weights)
    usable = {
        k: v for k, v in metric_scores.items() if v is not None and weights.get(k, 0) > 0
    }
    if not usable:
        return None, {"weights": weights, "used": {}, "missing": list(weights)}
    active_total = sum(weights[k] for k in usable)
    effective = {k: weights[k] / active_total for k in usable}
    score = sum(usable[k] * effective[k] for k in usable)
    return round(score, 4), {
        "weights": weights,
        "effective_weights": {k: round(v, 4) for k, v in effective.items()},
        "used": {k: round(v, 4) for k, v in usable.items()},
        "missing": [k for k in weights if k not in usable],
    }


def _mean(values: Sequence[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def aggregate_metric(
    results: Iterable[Any], metric: str
) -> dict[str, Any]:
    """Aggregate one metric across evaluation results (ORM objects or dicts)."""
    values: list[float] = []
    kinds: set[str] = set()
    judges: set[str] = set()
    unavailable = 0
    for result in results:
        entries = result.metrics if hasattr(result, "metrics") else result.get("metrics", [])
        for entry in entries:
            name = entry.metric if hasattr(entry, "metric") else entry.get("metric")
            if name != metric:
                continue
            available = (
                entry.available if hasattr(entry, "available") else entry.get("available", True)
            )
            score = (
                entry.normalized_score
                if hasattr(entry, "normalized_score")
                else entry.get("normalized_score")
            )
            kind = entry.kind if hasattr(entry, "kind") else entry.get("kind")
            judge = (
                entry.judge_model if hasattr(entry, "judge_model") else entry.get("judge_model")
            )
            if not available or score is None:
                unavailable += 1
                continue
            values.append(float(score))
            if kind:
                kinds.add(kind)
            if judge:
                judges.add(judge)
    spec = METRIC_SPECS.get(metric)
    return {
        "metric": metric,
        "label": spec.label if spec else metric,
        "mean": _mean(values),
        "median": round(statistics.median(values), 4) if values else None,
        "min": round(min(values), 4) if values else None,
        "max": round(max(values), 4) if values else None,
        "stdev": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0 if values else None,
        "sample_size": len(values),
        "unavailable_count": unavailable,
        "kinds": sorted(kinds),
        "judge_models": sorted(judges),
        "higher_is_better": spec.higher_is_better if spec else True,
    }


def summarise_results(
    results: Sequence[Any], metrics: Sequence[str], weights: dict[str, float] | None = None
) -> dict[str, Any]:
    """Build a summary block for a set of results (one run, or one model in a run)."""
    total = len(results)
    completed = [r for r in results if r.status == "completed"]
    errored = [r for r in results if r.status == "error"]
    failures = [r for r in results if r.passed is False]
    latencies = [r.latency_ms for r in completed if r.latency_ms is not None]
    composites = [r.composite_score for r in results if r.composite_score is not None]

    metric_summaries = {m: aggregate_metric(results, m) for m in metrics}
    quality_means = {
        m: s["mean"]
        for m, s in metric_summaries.items()
        if s["mean"] is not None and METRIC_SPECS.get(m, None) and METRIC_SPECS[m].group == "quality"
    }

    failure_breakdown: dict[str, int] = {}
    for result in results:
        failure = getattr(result, "failure", None)
        if failure is not None:
            failure_breakdown[failure.failure_type] = (
                failure_breakdown.get(failure.failure_type, 0) + 1
            )

    error_kinds: dict[str, int] = {}
    for result in errored:
        if result.error_kind:
            error_kinds[result.error_kind] = error_kinds.get(result.error_kind, 0) + 1

    return {
        "total_cases": total,
        "completed_cases": len(completed),
        "error_cases": len(errored),
        "failed_cases": len(failures),
        "passed_cases": sum(1 for r in results if r.passed is True),
        "failure_rate": round(len(failures) / total, 4) if total else None,
        "error_rate": round(len(errored) / total, 4) if total else None,
        "avg_latency_ms": _mean(latencies),
        "p95_latency_ms": (
            round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2)
            if latencies
            else None
        ),
        "min_latency_ms": round(min(latencies), 2) if latencies else None,
        "max_latency_ms": round(max(latencies), 2) if latencies else None,
        "avg_composite_score": _mean(composites),
        "avg_quality_score": _mean(list(quality_means.values())) if quality_means else None,
        "metrics": metric_summaries,
        "failure_breakdown": failure_breakdown,
        "error_kinds": error_kinds,
        "weights": normalise_weights(weights),
    }


def group_by_model(results: Sequence[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for result in results:
        key = f"{result.provider}/{result.model}"
        grouped.setdefault(key, []).append(result)
    return grouped
