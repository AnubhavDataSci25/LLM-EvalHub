"""Dashboard aggregation — every figure comes from stored results."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.logging import get_logger
from app.evaluation.aggregators import aggregate_metric, group_by_model, summarise_results
from app.evaluation.registry import METRIC_SPECS
from app.models.dataset import Dataset, Document, TestCase
from app.models.experiment import (
    EvaluationResult,
    EvaluationRun,
    Experiment,
    Failure,
)
from app.services.comparison_service import ComparisonService
from app.services.diagnosis_service import DiagnosisService
from app.services.provider_service import ProviderService

logger = get_logger(__name__)

HEADLINE_METRICS = ["correctness", "faithfulness", "answer_relevance"]


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _count(self, model, **filters) -> int:
        stmt = select(func.count()).select_from(model)
        for field, value in filters.items():
            stmt = stmt.where(getattr(model, field) == value)
        return int(self.db.execute(stmt).scalar_one())

    def build(self) -> dict[str, Any]:
        runs = list(
            self.db.execute(
                select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(50)
            ).scalars().all()
        )
        completed = [r for r in runs if r.status == "completed"]
        results = list(
            self.db.execute(
                select(EvaluationResult)
                .options(
                    selectinload(EvaluationResult.metrics),
                    selectinload(EvaluationResult.failure),
                )
                .order_by(EvaluationResult.created_at.desc())
                .limit(3000)
            ).scalars().unique().all()
        )

        kpis = self._kpis(results, runs)
        empty = kpis["evaluation_runs"] == 0

        return {
            "kpis": kpis,
            "judge_calibration": kpis.get("judge_calibration", {"calibrated": False, "kappa": None, "n_labels": 0}),
            "model_comparison": self._model_comparison(results),
            "metric_trend": self._metric_trend(completed),
            "failure_distribution": DiagnosisService(self.db).distribution(),
            "latency_distribution": self._latency_distribution(results),
            "score_distribution": self._score_distribution(results),
            "recent_runs": self._recent_runs(runs[:8]),
            "provider_status": ProviderService(self.db).describe_all(),
            "experiment_deltas": ComparisonService(self.db).recent_deltas(limit=4),
            "empty": empty,
        }

    def _kpis(self, results: list[EvaluationResult], runs: list[EvaluationRun]) -> dict[str, Any]:
        scored = [r for r in results if r.status == "completed"]
        latencies = [r.latency_ms for r in scored if r.latency_ms is not None]
        failures = [r for r in results if r.passed is False]
        errors = [r for r in results if r.status == "error"]
        metric_means = {
            metric: aggregate_metric(results, metric)["mean"] for metric in HEADLINE_METRICS
        }
        quality_values = [v for v in metric_means.values() if v is not None]

        from app.models.calibration import CalibrationRun

        latest_cal = self.db.execute(
            select(CalibrationRun)
            .where(CalibrationRun.status == "completed")
            .order_by(CalibrationRun.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_cal and latest_cal.agreement and latest_cal.agreement.get("kappa") is not None:
            judge_cal = {
                "calibrated": True,
                "kappa": latest_cal.agreement.get("kappa"),
                "n_labels": latest_cal.n_labels,
            }
        else:
            judge_cal = {
                "calibrated": False,
                "kappa": None,
                "n_labels": 0,
            }

        return {
            "datasets": self._count(Dataset),
            "test_cases": self._count(TestCase),
            "experiments": self._count(Experiment),
            "evaluation_runs": self._count(EvaluationRun),
            "completed_runs": sum(1 for r in runs if r.status == "completed"),
            "results": len(results),
            "failures": self._count(Failure),
            "documents": self._count(Document),
            "diagnosed_failures": int(
                self.db.execute(
                    select(func.count()).select_from(Failure).where(Failure.diagnosis.is_not(None))
                ).scalar_one()
            ),
            "judge_calibration": judge_cal,
            "avg_correctness": metric_means.get("correctness"),
            "avg_faithfulness": metric_means.get("faithfulness"),
            "avg_answer_relevance": metric_means.get("answer_relevance"),
            "avg_quality_score": (
                round(sum(quality_values) / len(quality_values), 4) if quality_values else None
            ),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "failure_rate": round(len(failures) / len(results), 4) if results else None,
            "error_rate": round(len(errors) / len(results), 4) if results else None,
        }

    def _model_comparison(self, results: list[EvaluationResult]) -> list[dict[str, Any]]:
        rows = []
        for key, group in group_by_model(results).items():
            metrics = sorted({m.metric for r in group for m in r.metrics})
            summary = summarise_results(group, metrics)
            sample = group[0]
            row = {
                "key": key,
                "provider": sample.provider,
                "model": sample.model,
                "label": sample.model_label or key,
                "cases": len(group),
                "avg_latency_ms": summary["avg_latency_ms"],
                "failure_rate": summary["failure_rate"],
                "composite": summary["avg_composite_score"],
            }
            for metric in METRIC_SPECS:
                block = summary["metrics"].get(metric)
                if block and block["mean"] is not None:
                    row[metric] = block["mean"]
            rows.append(row)
        rows.sort(key=lambda r: (r.get("composite") is None, -(r.get("composite") or 0)))
        return rows

    def _metric_trend(self, runs: list[EvaluationRun]) -> list[dict[str, Any]]:
        points = []
        for run in sorted(runs, key=lambda r: r.created_at)[-12:]:
            summary = run.summary or {}
            metrics = summary.get("metrics") or {}
            experiment = self.db.get(Experiment, run.experiment_id)
            point = {
                "run_id": run.id,
                "label": (experiment.name if experiment else run.id)[:28],
                "date": run.created_at.isoformat() if run.created_at else None,
                "failure_rate": summary.get("failure_rate"),
                "avg_latency_ms": summary.get("avg_latency_ms"),
                "quality": summary.get("avg_quality_score"),
            }
            for metric in HEADLINE_METRICS:
                point[metric] = (metrics.get(metric) or {}).get("mean")
            points.append(point)
        return points

    @staticmethod
    def _latency_distribution(results: list[EvaluationResult]) -> list[dict[str, Any]]:
        buckets = [
            ("<0.5s", 0, 500),
            ("0.5-1s", 500, 1000),
            ("1-2s", 1000, 2000),
            ("2-4s", 2000, 4000),
            ("4-8s", 4000, 8000),
            (">8s", 8000, float("inf")),
        ]
        counts = {label: 0 for label, _, _ in buckets}
        for result in results:
            if result.latency_ms is None:
                continue
            for label, low, high in buckets:
                if low <= result.latency_ms < high:
                    counts[label] += 1
                    break
        return [{"bucket": label, "count": counts[label]} for label, _, _ in buckets]

    @staticmethod
    def _score_distribution(results: list[EvaluationResult]) -> list[dict[str, Any]]:
        buckets = [("0.0-0.2", 0.0), ("0.2-0.4", 0.2), ("0.4-0.6", 0.4), ("0.6-0.8", 0.6), ("0.8-1.0", 0.8)]
        counts = {label: 0 for label, _ in buckets}
        for result in results:
            score = result.composite_score
            if score is None:
                continue
            for label, low in reversed(buckets):
                if score >= low:
                    counts[label] += 1
                    break
        return [{"bucket": label, "count": counts[label]} for label, _ in buckets]

    def _recent_runs(self, runs: list[EvaluationRun]) -> list[dict[str, Any]]:
        blocks = []
        for run in runs:
            experiment = self.db.get(Experiment, run.experiment_id)
            summary = run.summary or {}
            blocks.append(
                {
                    "id": run.id,
                    "experiment_id": run.experiment_id,
                    "experiment_name": experiment.name if experiment else None,
                    "status": run.status,
                    "progress": run.progress,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "duration_seconds": run.duration_seconds,
                    "total_units": run.total_units,
                    "quality": summary.get("avg_quality_score"),
                    "failure_rate": summary.get("failure_rate"),
                    "avg_latency_ms": summary.get("avg_latency_ms"),
                    "models": summary.get("models", []),
                }
            )
        return blocks
