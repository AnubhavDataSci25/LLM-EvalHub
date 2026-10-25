"""Evaluation execution service.

Flow (matching the documented execution strategy):

    POST /api/evaluations/run
        -> create EvaluationRun (status=queued), return the run id immediately
        -> background task executes the LangGraph workflow per work unit
        -> results persist progressively so the UI can poll partial progress
        -> run finishes with an aggregated summary

Concurrency is bounded by MAX_CONCURRENT_REQUESTS; retries are bounded by
RETRY_ATTEMPTS. A failing unit is recorded as an errored result, never an
exception that kills the run.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.concurrency import run_bounded
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.db.base import new_id
from app.db.session import session_scope
from app.evaluation.aggregators import group_by_model, normalise_weights, summarise_results
from app.evaluation.judge import JudgeConfig, LLMJudge
from app.evaluation.ragas_adapter import build_ragas_adapter
from app.evaluation.registry import Evaluator
from app.models.dataset import TestCase
from app.models.experiment import (
    EvaluationResult,
    EvaluationRun,
    Experiment,
    Failure,
    MetricResult,
)
from app.providers.registry import get_provider
from app.rag.embeddings import get_embedder
from app.rag.retriever import Retriever
from app.schemas.experiment import RunEvaluationRequest
from app.services.dataset_service import DatasetService
from app.services.experiment_service import ExperimentService
from app.workflows.evaluation_graph import EvaluationGraph
from app.workflows.state import EvaluationState

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalise before arithmetic."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class EvaluationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.datasets = DatasetService(db)
        self.experiments = ExperimentService(db)

    # -- run lifecycle ----------------------------------------------------
    def get_run(self, run_id: str) -> EvaluationRun:
        run = self.db.get(EvaluationRun, run_id)
        if run is None:
            raise NotFoundError(f"Evaluation run '{run_id}' was not found.")
        return run

    def list_runs(
        self, *, limit: int = 50, offset: int = 0, experiment_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[EvaluationRun], int]:
        stmt = select(EvaluationRun)
        if experiment_id:
            stmt = stmt.where(EvaluationRun.experiment_id == experiment_id)
        if status:
            stmt = stmt.where(EvaluationRun.status == status)
        total = int(
            self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        )
        stmt = stmt.order_by(EvaluationRun.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all()), total

    def results(
        self,
        run_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        failed_only: bool = False,
        model: str | None = None,
        provider: str | None = None,
        search: str | None = None,
    ) -> tuple[list[EvaluationResult], int]:
        stmt = (
            select(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
            .options(
                selectinload(EvaluationResult.metrics),
                selectinload(EvaluationResult.failure),
            )
        )
        if status:
            stmt = stmt.where(EvaluationResult.status == status)
        if failed_only:
            stmt = stmt.where(EvaluationResult.passed.is_(False))
        if model:
            stmt = stmt.where(EvaluationResult.model == model)
        if provider:
            stmt = stmt.where(EvaluationResult.provider == provider)
        if search:
            stmt = stmt.where(EvaluationResult.question.ilike(f"%{search.strip()}%"))
        total = int(
            self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        )
        stmt = stmt.order_by(EvaluationResult.created_at)
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().unique().all()), total

    def enrich_run(self, run: EvaluationRun) -> dict[str, Any]:
        experiment = self.db.get(Experiment, run.experiment_id)
        dataset = None
        if experiment:
            from app.models.dataset import Dataset

            dataset = self.db.get(Dataset, experiment.dataset_id)
        return {
            **{c.name: getattr(run, c.name) for c in EvaluationRun.__table__.columns},
            "experiment_name": experiment.name if experiment else None,
            "dataset_id": experiment.dataset_id if experiment else None,
            "dataset_name": dataset.name if dataset else None,
        }

    # -- creation ---------------------------------------------------------
    def create_run(self, payload: RunEvaluationRequest) -> EvaluationRun:
        if payload.experiment_id:
            experiment = self.experiments.get(payload.experiment_id)
        else:
            experiment = self.experiments.create(payload.experiment)  # type: ignore[arg-type]

        cases = self.datasets.test_cases(experiment.dataset_version_id)
        if payload.case_ids:
            wanted = set(payload.case_ids)
            cases = [c for c in cases if c.id in wanted]
        if not cases:
            raise ValidationFailedError("No test cases selected for this run.")

        total_units = len(cases) * max(1, len(experiment.models))
        run = EvaluationRun(
            id=new_id("run"),
            experiment_id=experiment.id,
            status="queued",
            total_units=total_units,
            completed_units=0,
            stage="queued",
            config_snapshot=self._snapshot(experiment, cases, payload),
        )
        self.db.add(run)
        self.db.flush()
        logger.info("queued run %s (%s units)", run.id, total_units)
        return run

    def _snapshot(
        self, experiment: Experiment, cases: list[TestCase], payload: RunEvaluationRequest
    ) -> dict[str, Any]:
        """Everything needed to reproduce this run, frozen at submission time."""
        return {
            "experiment_id": experiment.id,
            "experiment_name": experiment.name,
            "dataset_id": experiment.dataset_id,
            "dataset_version_id": experiment.dataset_version_id,
            "case_count": len(cases),
            "case_ids": [c.id for c in cases] if payload.case_ids else None,
            "models": [
                {"provider": m.provider, "model": m.model, "label": m.label}
                for m in experiment.models
            ],
            "metrics": list(experiment.metrics or []),
            "metric_weights": normalise_weights(experiment.metric_weights),
            "prompt_label": experiment.prompt_label,
            "system_prompt": experiment.system_prompt,
            "prompt_template": experiment.prompt_template,
            "temperature": experiment.temperature,
            "max_tokens": experiment.max_tokens,
            "rag": {
                "enabled": experiment.rag_enabled,
                "collection": experiment.rag_collection,
                "retriever": experiment.retriever,
                "chunk_size": experiment.chunk_size,
                "chunk_overlap": experiment.chunk_overlap,
                "top_k": experiment.top_k,
                "embedding_backend": experiment.embedding_model,
            },
            "judge": {
                "provider": experiment.judge_provider,
                "model": experiment.judge_model,
            },
            "latency_budget_ms": payload.latency_budget_ms,
            "concurrency_limit": settings.max_concurrent_requests,
            "retry_attempts": settings.retry_attempts,
            "submitted_at": _utcnow().isoformat(),
        }


# ---------------------------------------------------------------------------
# background execution (owns its own session)
# ---------------------------------------------------------------------------
class EvaluationRunner:
    """Executes a queued run. Runs in a background task with its own session."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    async def execute(self) -> None:
        with session_scope() as db:
            run = db.get(EvaluationRun, self.run_id)
            if run is None:
                logger.error("run %s disappeared before execution", self.run_id)
                return
            if run.status not in {"queued", "failed"}:
                logger.info("run %s already %s; skipping", run.id, run.status)
                return
            experiment = db.get(Experiment, run.experiment_id)
            if experiment is None:
                run.status = "failed"
                run.error = "Experiment no longer exists."
                return

            run.status = "running"
            run.started_at = _utcnow()
            run.stage = "starting"
            db.flush()
            db.commit()

            try:
                await self._run_units(db, run, experiment)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("run %s failed", run.id)
                run.status = "failed"
                run.error = str(exc)[:1000]
                run.finished_at = _utcnow()
                db.flush()

    async def _run_units(
        self, db: Session, run: EvaluationRun, experiment: Experiment
    ) -> None:
        service = EvaluationService(db)
        snapshot = run.config_snapshot or {}
        cases = service.datasets.test_cases(experiment.dataset_version_id)
        selected = snapshot.get("case_ids")
        if selected:
            wanted = set(selected)
            cases = [c for c in cases if c.id in wanted]

        warnings: list[str] = []
        providers: dict[str, Any] = {}
        for model in experiment.models:
            if model.provider in providers:
                continue
            provider = get_provider(model.provider)
            if not provider.is_configured:
                warnings.append(
                    f"Provider '{model.provider}' is not configured; its results are recorded "
                    "as provider errors."
                )
            providers[model.provider] = provider

        judge = None
        judge_config = None
        if experiment.judge_provider and experiment.judge_model and settings.enable_llm_judge:
            judge_provider = get_provider(experiment.judge_provider)
            if judge_provider.is_configured:
                judge_config = JudgeConfig(
                    provider=judge_provider, model=experiment.judge_model
                )
                judge = LLMJudge(judge_config)
            else:
                warnings.append(
                    f"Judge provider '{experiment.judge_provider}' is not configured; "
                    "quality metrics fall back to deterministic evaluators."
                )

        ragas = build_ragas_adapter(judge_config, settings.enable_ragas)
        evaluator = Evaluator(list(experiment.metrics or []), judge=judge, ragas_adapter=ragas)

        retriever_cache: dict[str, Retriever] = {}

        async def retriever_factory(collection: str, strategy: str, top_k: int) -> Retriever:
            key = f"{collection}:{strategy}:{top_k}"
            if key not in retriever_cache:
                retriever = Retriever(
                    db,
                    collection,
                    strategy=strategy,
                    top_k=top_k,
                    embedder=get_embedder(experiment.embedding_model),
                    vector_backend=settings.vector_store_backend,
                )
                await retriever.prepare()
                retriever_cache[key] = retriever
            return retriever_cache[key]

        progress_state = {"done": 0}

        async def persist(state: EvaluationState) -> None:
            self._persist_result(db, run, state)
            progress_state["done"] += 1
            run.completed_units = progress_state["done"]
            run.progress = round(progress_state["done"] / max(1, run.total_units), 4)
            run.stage = "evaluating"
            db.flush()
            if progress_state["done"] % 5 == 0:
                db.commit()  # progressive persistence for polling clients

        graph = EvaluationGraph(
            providers=providers,
            evaluator=evaluator,
            retriever_factory=retriever_factory if experiment.rag_enabled else None,
            persist=persist,
            weights=experiment.metric_weights,
            latency_budget_ms=float(snapshot.get("latency_budget_ms", 4000.0)),
            timeout_seconds=float(settings.request_timeout_seconds),
        )

        units: list[EvaluationState] = []
        for model in experiment.models:
            for case in cases:
                units.append(
                    EvaluationState(
                        run_id=run.id,
                        experiment_id=experiment.id,
                        dataset_id=experiment.dataset_id,
                        test_case_id=case.id,
                        provider=model.provider,
                        model=model.model,
                        model_label=model.label,
                        question=case.question,
                        ground_truth=case.ground_truth,
                        inline_context=case.context,
                        system_prompt=experiment.system_prompt,
                        prompt_template=experiment.prompt_template,
                        temperature=experiment.temperature,
                        max_tokens=experiment.max_tokens,
                        rag_enabled=experiment.rag_enabled,
                        collection=experiment.rag_collection,
                        retriever_strategy=experiment.retriever,
                        top_k=experiment.top_k,
                        status="pending",
                        warnings=[],
                    )
                )

        async def worker(unit: EvaluationState) -> None:
            try:
                await graph.run(unit)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("unit failed unexpectedly")
                unit["status"] = "error"
                unit["error_kind"] = "unexpected_error"
                unit["error_message"] = str(exc)[:500]
                await persist(unit)

        await run_bounded(units, worker, limit=settings.max_concurrent_requests)

        db.flush()
        results, _ = service.results(run.id)
        run.summary = self._build_summary(results, experiment)
        run.status = "completed"
        run.stage = "completed"
        run.progress = 1.0
        run.completed_units = len(results)
        run.finished_at = _utcnow()
        started = _as_aware(run.started_at)
        finished = _as_aware(run.finished_at)
        if started and finished:
            run.duration_seconds = round((finished - started).total_seconds(), 3)
        collected = list(dict.fromkeys(warnings))
        for result in results:
            for warning in (result.raw_meta or {}).get("warnings", []):
                if warning not in collected:
                    collected.append(warning)
        run.warnings = collected[:20]
        db.flush()
        logger.info("run %s completed: %s results", run.id, len(results))

    # -- persistence ------------------------------------------------------
    @staticmethod
    def _persist_result(db: Session, run: EvaluationRun, state: EvaluationState) -> None:
        status = state.get("status") or "completed"
        result = EvaluationResult(
            id=new_id("res"),
            run_id=run.id,
            experiment_id=state["experiment_id"],
            test_case_id=state["test_case_id"],
            provider=state["provider"],
            model=state["model"],
            model_label=state.get("model_label"),
            question=state.get("question", ""),
            ground_truth=state.get("ground_truth"),
            generated_answer=state.get("generated_answer"),
            retrieved_context=list(state.get("retrieved_context") or []),
            retrieval_meta=state.get("retrieval_meta") or {},
            status="error" if status == "error" else "completed",
            passed=state.get("passed"),
            latency_ms=state.get("latency_ms"),
            composite_score=state.get("composite_score"),
            usage=state.get("usage") or {},
            error_kind=state.get("error_kind"),
            error_message=state.get("error_message"),
            raw_meta={
                "finish_reason": state.get("finish_reason"),
                "resolved_model": state.get("resolved_model"),
                "composite_breakdown": state.get("composite_breakdown") or {},
                "prompt": (state.get("rendered_prompt") or "")[:4000],
                "warnings": state.get("warnings") or [],
            },
        )
        db.add(result)

        for outcome in state.get("metric_outcomes") or []:
            evidence_val = outcome.evidence
            if outcome.kind == "llm_judge":
                prov, mod = "", ""
                if outcome.judge_model and "/" in outcome.judge_model:
                    prov, mod = outcome.judge_model.split("/", 1)
                elif outcome.judge_model:
                    prov, mod = "mock", outcome.judge_model

                rel = None
                if prov and mod:
                    try:
                        from app.services.calibration_service import CalibrationService

                        rel = CalibrationService(db).get_reliability(prov, mod, outcome.metric)
                    except Exception:
                        rel = None

                rel_payload = {
                    "status": "calibrated" if rel else "uncalibrated",
                    "kappa": rel.get("kappa") if rel else None,
                    "interval": rel.get("interval") if rel else None,
                    "n_labels": rel.get("n_labels", 0) if rel else 0,
                }

                if evidence_val and evidence_val.strip().startswith("{"):
                    try:
                        import json

                        parsed = json.loads(evidence_val)
                        if isinstance(parsed, dict):
                            parsed["judge_reliability"] = rel_payload
                            evidence_val = json.dumps(parsed)
                        else:
                            evidence_val = json.dumps(
                                {"reasoning": evidence_val, "judge_reliability": rel_payload}
                            )
                    except Exception:
                        evidence_val = json.dumps(
                            {"reasoning": evidence_val, "judge_reliability": rel_payload}
                        )
                else:
                    import json

                    evidence_val = json.dumps(
                        {"reasoning": evidence_val, "judge_reliability": rel_payload}
                    )

            db.add(
                MetricResult(
                    id=new_id("mr"),
                    result_id=result.id,
                    metric=outcome.metric,
                    kind=outcome.kind,
                    raw_score=outcome.raw_score,
                    normalized_score=outcome.normalized_score,
                    confidence=outcome.confidence,
                    judge_model=outcome.judge_model,
                    evidence=evidence_val,
                    available=outcome.available,
                    unavailable_reason=outcome.unavailable_reason,
                )
            )

        failure = state.get("failure")
        if failure:
            db.add(
                Failure(
                    id=new_id("fail"),
                    result_id=result.id,
                    run_id=run.id,
                    experiment_id=state["experiment_id"],
                    failure_type=failure["failure_type"],
                    severity=failure.get("severity", "medium"),
                    detector=failure.get("detector", "rule"),
                    confidence=float(failure.get("confidence", 0.5)),
                    evidence=list(failure.get("evidence") or []),
                    signals=failure.get("signals") or {},
                )
            )

    @staticmethod
    def _build_summary(results: list[EvaluationResult], experiment: Experiment) -> dict[str, Any]:
        metrics = list(experiment.metrics or [])
        weights = experiment.metric_weights
        overall = summarise_results(results, metrics, weights)
        per_model = {}
        for key, group in group_by_model(results).items():
            block = summarise_results(group, metrics, weights)
            sample = group[0]
            block["provider"] = sample.provider
            block["model"] = sample.model
            block["label"] = sample.model_label or key
            per_model[key] = block
        overall["per_model"] = per_model
        overall["models"] = sorted(per_model.keys())
        return overall


async def execute_run(run_id: str) -> None:
    """Entry point used by FastAPI background tasks."""
    await EvaluationRunner(run_id).execute()


def execute_run_sync(run_id: str) -> None:
    """Sync wrapper so BackgroundTasks can schedule the coroutine safely."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(execute_run(run_id))
        return
    asyncio.create_task(execute_run(run_id))  # pragma: no cover
