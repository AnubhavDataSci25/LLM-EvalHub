"""Report generation.

A report is a frozen snapshot of what a run measured, assembled entirely from
stored results — never recomputed from live provider calls, so a report stays
valid and reproducible after the fact.

Exports: JSON (the full structure) and CSV (the per-case result table). The web
report is the primary artefact; PDF is intentionally out of MVP scope.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.base import new_id
from app.evaluation.registry import METRIC_SPECS
from app.models.analysis import Report
from app.models.dataset import Dataset
from app.models.experiment import Experiment
from app.schemas.experiment import RecommendationRequest, ReportRequest
from app.services.comparison_service import ComparisonService
from app.services.dataset_service import DatasetService
from app.services.diagnosis_service import DiagnosisService
from app.services.evaluation_service import EvaluationService
from app.services.recommendation_service import RecommendationService

logger = get_logger(__name__)


class ReportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.evaluations = EvaluationService(db)
        self.comparisons = ComparisonService(db)
        self.diagnosis = DiagnosisService(db)
        self.datasets = DatasetService(db)

    def get(self, report_id: str) -> Report:
        report = self.db.get(Report, report_id)
        if report is None:
            raise NotFoundError(f"Report '{report_id}' was not found.")
        return report

    def list(self, *, limit: int = 50) -> list[Report]:
        return list(
            self.db.execute(select(Report).order_by(Report.created_at.desc()).limit(limit))
            .scalars()
            .all()
        )

    def delete(self, report_id: str) -> None:
        self.db.delete(self.get(report_id))
        self.db.flush()

    # -- generation --------------------------------------------------------
    def generate(self, payload: ReportRequest) -> Report:
        run = self.evaluations.get_run(payload.run_id)
        experiment = self.db.get(Experiment, run.experiment_id)
        dataset = self.db.get(Dataset, experiment.dataset_id) if experiment else None
        results, _ = self.evaluations.results(run.id)
        summary = run.summary or {}

        model_comparison = self.comparisons.compare_models(run.id)

        failures_block: list[dict[str, Any]] = []
        if payload.include_failures:
            failures, _ = self.diagnosis.list_failures(run_id=run.id, limit=payload.max_failures)
            for failure in failures:
                result = failure.result
                failures_block.append(
                    {
                        "failure_id": failure.id,
                        "failure_type": failure.failure_type,
                        "severity": failure.severity,
                        "confidence": failure.confidence,
                        "detector": failure.detector,
                        "evidence": failure.evidence,
                        "diagnosis": failure.diagnosis,
                        "diagnosis_source": failure.diagnosis_source,
                        "provider": result.provider if result else None,
                        "model": result.model if result else None,
                        "question": (result.question if result else "")[:400],
                        "expected": (result.ground_truth if result else None),
                        "generated": (result.generated_answer if result else None),
                        "scores": result.metric_map if result else {},
                    }
                )

        recommendation_block = None
        if payload.include_recommendation:
            try:
                service = RecommendationService(self.db)
                recommendation = service.build(
                    RecommendationRequest(
                        use_case=(experiment.benchmark_pack_key if experiment else None) or "general",
                        profile="balanced",
                        run_ids=[run.id],
                        min_sample_size=1,
                    )
                )
                recommendation_block = {
                    "id": recommendation.id,
                    "recommended_provider": recommendation.recommended_provider,
                    "recommended_model": recommendation.recommended_model,
                    "recommended_score": recommendation.recommended_score,
                    "weights": recommendation.weights,
                    "rationale": recommendation.rationale,
                    "evidence": recommendation.evidence,
                    "caveats": recommendation.caveats,
                    "candidates": recommendation.candidates,
                }
            except Exception as exc:
                logger.info("recommendation skipped in report: %s", exc)
                recommendation_block = {
                    "unavailable_reason": str(exc)[:300],
                }

        before_after = None
        if payload.baseline_run_id:
            before_after = self.comparisons.improvement_summary(payload.baseline_run_id, run.id)

        rag_block = self._rag_block(results, experiment, summary)
        findings = self._findings(summary, model_comparison, failures_block, rag_block)
        next_steps = self._next_steps(failures_block, summary, rag_block)

        judge_reliability_block: dict[str, Any] | None = None
        if experiment and experiment.judge_provider and experiment.judge_model:
            from app.services.calibration_service import CalibrationService

            cal_service = CalibrationService(self.db)
            rel = None
            for m in experiment.metrics or ["correctness"]:
                rel = cal_service.get_reliability(
                    experiment.judge_provider, experiment.judge_model, m
                )
                if rel:
                    break

            if rel:
                judge_reliability_block = {
                    "calibrated": True,
                    "judge_provider": experiment.judge_provider,
                    "judge_model": experiment.judge_model,
                    "metric": rel.get("metric"),
                    "kappa": rel.get("kappa"),
                    "interval": rel.get("interval"),
                    "n_labels": rel.get("n_labels"),
                    "interpretation": rel.get("interpretation"),
                    "probe_results": rel.get("probes", {}),
                    "warnings": rel.get("warnings", []),
                }
                findings.append(
                    f"Judge reliability ({experiment.judge_provider}/{experiment.judge_model}): "
                    f"Cohen's kappa {rel.get('kappa'):.2f} (95% CI {rel.get('interval') or 'NA'}, "
                    f"N={rel.get('n_labels')}, {rel.get('interpretation')})."
                )
            else:
                judge_reliability_block = {
                    "calibrated": False,
                    "judge_provider": experiment.judge_provider,
                    "judge_model": experiment.judge_model,
                    "status": "uncalibrated",
                    "kappa": None,
                    "n_labels": 0,
                    "probe_results": {},
                    "warnings": [
                        "No human agreement calibration exists for this judge on this dataset."
                    ],
                }
                findings.append(
                    f"LLM judge ({experiment.judge_provider}/{experiment.judge_model}) is uncalibrated on this dataset; "
                    "no human agreement has been measured."
                )

        attribution_block = None
        if experiment:
            from app.models.attribution import AttributionRun

            att_runs = list(
                self.db.execute(
                    select(AttributionRun).where(AttributionRun.experiment_id == experiment.id)
                ).scalars().all()
            )
            v_counts: dict[str, int] = {}
            for ar in att_runs:
                v_counts[ar.verdict] = v_counts.get(ar.verdict, 0) + 1
            total_att = len(att_runs)
            retrieval_share = (
                round(v_counts.get("RETRIEVAL_CAUSED", 0) / total_att, 4) if total_att > 0 else 0.0
            )
            generation_share = (
                round(v_counts.get("GENERATION_CAUSED", 0) / total_att, 4) if total_att > 0 else 0.0
            )
            attribution_block = {
                "total_attributed": total_att,
                "total_failures": summary.get("failed_cases", 0),
                "verdict_counts": v_counts,
                "retrieval_caused_share": retrieval_share,
                "generation_caused_share": generation_share,
                "limitations": [
                    "Attribution applies counterfactual controls to individual failed test cases; results reflect those specific cases, not general model performance.",
                    "Attribution depends on the fidelity of gold context passages in test cases.",
                    "Single-trial runs (N=1) do not capture LLM stochastic generation variance; N=3-5 repeats recommended for noisy tasks.",
                ],
            }
            if total_att > 0:
                findings.append(
                    f"Counterfactual attribution on {total_att} failure(s): "
                    f"{retrieval_share:.0%} retrieval-caused, {generation_share:.0%} generation-caused."
                )

        content: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "experiment": self._experiment_block(experiment, dataset),
            "run": {
                "id": run.id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "duration_seconds": run.duration_seconds,
                "total_units": run.total_units,
                "completed_units": run.completed_units,
                "warnings": run.warnings or [],
                "config_snapshot": run.config_snapshot or {},
            },
            "dataset": self._dataset_block(dataset, experiment),
            "models_tested": model_comparison.get("rows", []),
            "metrics": self._metrics_block(summary),
            "metric_definitions": {
                m: METRIC_SPECS[m].as_dict() for m in summary.get("metrics", {}) if m in METRIC_SPECS
            },
            "latency": {
                "avg_ms": summary.get("avg_latency_ms"),
                "p95_ms": summary.get("p95_latency_ms"),
                "min_ms": summary.get("min_latency_ms"),
                "max_ms": summary.get("max_latency_ms"),
                "per_model": {
                    row["key"]: {
                        "avg_ms": row["avg_latency_ms"],
                        "p95_ms": row["p95_latency_ms"],
                    }
                    for row in model_comparison.get("rows", [])
                },
            },
            "failures": {
                "total": summary.get("failed_cases"),
                "rate": summary.get("failure_rate"),
                "breakdown": summary.get("failure_breakdown", {}),
                "error_kinds": summary.get("error_kinds", {}),
                "cases": failures_block,
            },
            "attribution": attribution_block,
            "rag": rag_block,
            "judge_reliability": judge_reliability_block,
            "recommendation": recommendation_block,
            "before_after": before_after,
            "findings": findings,
            "next_steps": next_steps,
        }

        report = Report(
            id=new_id("rep"),
            title=payload.title or f"Evaluation report — {experiment.name if experiment else run.id}",
            run_id=run.id,
            experiment_id=run.experiment_id,
            baseline_run_id=payload.baseline_run_id,
            kind="improvement" if payload.baseline_run_id else "evaluation",
            content=content,
        )
        self.db.add(report)
        self.db.flush()
        logger.info("generated report %s for run %s", report.id, run.id)
        return report

    # -- blocks ------------------------------------------------------------
    @staticmethod
    def _experiment_block(experiment: Experiment | None, dataset: Dataset | None) -> dict[str, Any]:
        if experiment is None:
            return {}
        return {
            "id": experiment.id,
            "name": experiment.name,
            "description": experiment.description,
            "origin": experiment.origin,
            "parent_experiment_id": experiment.parent_experiment_id,
            "change_summary": experiment.change_summary,
            "prompt_label": experiment.prompt_label,
            "system_prompt": experiment.system_prompt,
            "prompt_template": experiment.prompt_template,
            "temperature": experiment.temperature,
            "max_tokens": experiment.max_tokens,
            "metrics": experiment.metrics,
            "metric_weights": experiment.metric_weights,
            "judge": {"provider": experiment.judge_provider, "model": experiment.judge_model},
            "rag": {
                "enabled": experiment.rag_enabled,
                "collection": experiment.rag_collection,
                "retriever": experiment.retriever,
                "chunk_size": experiment.chunk_size,
                "chunk_overlap": experiment.chunk_overlap,
                "top_k": experiment.top_k,
                "embedding_backend": experiment.embedding_model,
            },
        }

    def _dataset_block(self, dataset: Dataset | None, experiment: Experiment | None) -> dict[str, Any]:
        if dataset is None or experiment is None:
            return {}
        cases = self.datasets.test_cases(experiment.dataset_version_id)
        difficulties: dict[str, int] = {}
        categories: dict[str, int] = {}
        for case in cases:
            difficulties[case.difficulty or "unspecified"] = (
                difficulties.get(case.difficulty or "unspecified", 0) + 1
            )
            if case.category:
                categories[case.category] = categories.get(case.category, 0) + 1
        return {
            "id": dataset.id,
            "name": dataset.name,
            "description": dataset.description,
            "domain": dataset.domain,
            "version_id": experiment.dataset_version_id,
            "case_count": len(cases),
            "with_ground_truth": sum(1 for c in cases if c.ground_truth),
            "with_context": sum(1 for c in cases if c.context),
            "difficulty_mix": difficulties,
            "categories": categories,
            "benchmark_pack_key": dataset.benchmark_pack_key,
        }

    @staticmethod
    def _metrics_block(summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "overall": {
                "total_cases": summary.get("total_cases"),
                "completed_cases": summary.get("completed_cases"),
                "error_cases": summary.get("error_cases"),
                "failed_cases": summary.get("failed_cases"),
                "failure_rate": summary.get("failure_rate"),
                "error_rate": summary.get("error_rate"),
                "avg_quality_score": summary.get("avg_quality_score"),
                "avg_composite_score": summary.get("avg_composite_score"),
                "weights": summary.get("weights", {}),
            },
            "per_metric": summary.get("metrics", {}),
            "per_model": summary.get("per_model", {}),
        }

    @staticmethod
    def _rag_block(results, experiment: Experiment | None, summary: dict[str, Any]) -> dict[str, Any]:
        if experiment is None or not experiment.rag_enabled:
            return {"enabled": False}
        retrieved_counts = [
            len(r.retrieved_context or []) for r in results if r.retrieved_context is not None
        ]
        empty_retrievals = sum(1 for c in retrieved_counts if c == 0)
        metrics = summary.get("metrics", {})
        return {
            "enabled": True,
            "collection": experiment.rag_collection,
            "retriever": experiment.retriever,
            "top_k": experiment.top_k,
            "chunk_size": experiment.chunk_size,
            "chunk_overlap": experiment.chunk_overlap,
            "embedding_backend": experiment.embedding_model,
            "avg_chunks_retrieved": (
                round(sum(retrieved_counts) / len(retrieved_counts), 2) if retrieved_counts else 0
            ),
            "empty_retrievals": empty_retrievals,
            "context_precision": (metrics.get("context_precision") or {}).get("mean"),
            "context_recall": (metrics.get("context_recall") or {}).get("mean"),
            "retrieval_hit_rate": (metrics.get("retrieval_hit_rate") or {}).get("mean"),
        }

    @staticmethod
    def _findings(
        summary: dict[str, Any],
        model_comparison: dict[str, Any],
        failures: list[dict[str, Any]],
        rag: dict[str, Any],
    ) -> list[str]:
        findings: list[str] = []
        rows = model_comparison.get("rows", [])
        if len(rows) > 1:
            best, worst = rows[0], rows[-1]
            if best.get("avg_composite_score") and worst.get("avg_composite_score"):
                findings.append(
                    f"{best['label']} scored highest on the composite metric "
                    f"({best['avg_composite_score']:.3f}) and {worst['label']} lowest "
                    f"({worst['avg_composite_score']:.3f}) on identical inputs."
                )
            latencies = [(r["label"], r["avg_latency_ms"]) for r in rows if r["avg_latency_ms"]]
            if len(latencies) > 1:
                fastest = min(latencies, key=lambda x: x[1])
                slowest = max(latencies, key=lambda x: x[1])
                findings.append(
                    f"Latency ranged from {fastest[1]:.0f} ms ({fastest[0]}) to "
                    f"{slowest[1]:.0f} ms ({slowest[0]})."
                )
        rate = summary.get("failure_rate")
        if rate is not None:
            findings.append(
                f"{summary.get('failed_cases', 0)} of {summary.get('total_cases', 0)} cases "
                f"were flagged as failures ({rate:.0%})."
            )
        breakdown = summary.get("failure_breakdown") or {}
        if breakdown:
            top = max(breakdown.items(), key=lambda kv: kv[1])
            findings.append(
                f"The most common failure category was '{top[0].replace('_', ' ')}' "
                f"({top[1]} case(s))."
            )
        if summary.get("error_cases"):
            findings.append(
                f"{summary['error_cases']} case(s) failed at the provider and were excluded from "
                "quality scoring."
            )
        if rag.get("enabled"):
            recall = rag.get("context_recall")
            precision = rag.get("context_precision")
            if recall is not None and precision is not None:
                findings.append(
                    f"Retrieval scored {recall:.2f} recall and {precision:.2f} precision at "
                    f"top_k={rag.get('top_k')}."
                )
            if rag.get("empty_retrievals"):
                findings.append(
                    f"{rag['empty_retrievals']} case(s) retrieved no context at all."
                )
        unavailable = [
            name
            for name, block in (summary.get("metrics") or {}).items()
            if block.get("mean") is None
        ]
        if unavailable:
            findings.append(
                "These metrics could not be computed for this run: " + ", ".join(unavailable) + "."
            )
        return findings

    @staticmethod
    def _next_steps(
        failures: list[dict[str, Any]], summary: dict[str, Any], rag: dict[str, Any]
    ) -> list[str]:
        steps: list[str] = []
        breakdown = summary.get("failure_breakdown") or {}
        if breakdown.get("poor_retrieval"):
            steps.append(
                f"Retrieval caused {breakdown['poor_retrieval']} failure(s). Try raising top_k "
                "or increasing chunk overlap, then re-run and compare."
            )
        if breakdown.get("hallucination") or breakdown.get("unsupported_claim"):
            count = breakdown.get("hallucination", 0) + breakdown.get("unsupported_claim", 0)
            steps.append(
                f"{count} answer(s) contained unsupported content. Strengthen the grounding "
                "instruction and require an explicit refusal when context is insufficient."
            )
        if breakdown.get("incorrect_answer") or breakdown.get("missing_information"):
            steps.append(
                "Answer-quality failures dominate. Compare a stronger model on the same dataset "
                "before iterating further on the prompt."
            )
        if breakdown.get("timeout") or summary.get("error_rate"):
            steps.append(
                "Some cases failed at the provider. Re-run the failed subset once quota recovers "
                "so the comparison is complete."
            )
        undiagnosed = sum(1 for f in failures if not f.get("diagnosis"))
        if undiagnosed:
            steps.append(f"Run AI diagnosis on the {undiagnosed} failure(s) that lack one.")
        if not steps:
            steps.append(
                "No systematic failure pattern stands out. Expand the dataset or add a harder "
                "category to increase discriminating power."
            )
        return steps

    # -- exports -----------------------------------------------------------
    def export_json(self, report: Report) -> str:
        return json.dumps(
            {
                "id": report.id,
                "title": report.title,
                "kind": report.kind,
                "run_id": report.run_id,
                "experiment_id": report.experiment_id,
                "baseline_run_id": report.baseline_run_id,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "content": report.content,
            },
            indent=2,
            default=str,
        )

    def export_csv(self, report: Report) -> str:
        """Per-case result table — the shape people paste into a spreadsheet."""
        if not report.run_id:
            return ""
        results, _ = self.evaluations.results(report.run_id)
        metric_names = sorted({m.metric for r in results for m in r.metrics})
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "result_id",
                "provider",
                "model",
                "status",
                "passed",
                "failure_type",
                "latency_ms",
                "composite_score",
                "question",
                "expected_answer",
                "generated_answer",
                "retrieved_chunks",
                "error_kind",
                *metric_names,
            ]
        )
        for result in results:
            scores = {m.metric: m.normalized_score for m in result.metrics if m.available}
            writer.writerow(
                [
                    result.id,
                    result.provider,
                    result.model,
                    result.status,
                    result.passed,
                    result.failure.failure_type if result.failure else "",
                    round(result.latency_ms, 2) if result.latency_ms else "",
                    result.composite_score if result.composite_score is not None else "",
                    (result.question or "").replace("\n", " "),
                    (result.ground_truth or "").replace("\n", " "),
                    (result.generated_answer or "").replace("\n", " "),
                    len(result.retrieved_context or []),
                    result.error_kind or "",
                    *[
                        "" if scores.get(name) is None else round(scores[name], 4)
                        for name in metric_names
                    ],
                ]
            )
        return buffer.getvalue()
