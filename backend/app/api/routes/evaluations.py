"""Experiment, evaluation, comparison, failure, recommendation and report routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Response, UploadFile

from app.api.deps import DbSession, PageParams
from app.core.exceptions import ValidationFailedError
from app.schemas.common import Acknowledgement
from app.schemas.dashboard import DashboardResponse
from app.schemas.dataset import (
    DocumentIndexRequest,
    DocumentRead,
    RetrievalPreviewRequest,
)
from app.schemas.experiment import (
    ComparisonRequest,
    DiagnoseRequest,
    EvaluationResultRead,
    EvaluationRunRead,
    ExperimentCreate,
    ExperimentRead,
    FailureRead,
    ImprovementRequest,
    RecommendationRead,
    RecommendationRequest,
    ReportRead,
    ReportRequest,
    RunEvaluationRequest,
)
from app.services.comparison_service import ComparisonService
from app.services.dashboard_service import DashboardService
from app.services.diagnosis_service import DiagnosisService
from app.services.evaluation_service import EvaluationService, execute_run
from app.services.experiment_service import ExperimentService
from app.services.improvement_service import ImprovementService
from app.services.rag_service import RagService
from app.services.recommendation_service import RecommendationService
from app.services.report_service import ReportService

experiments_router = APIRouter(prefix="/experiments", tags=["experiments"])
evaluations_router = APIRouter(prefix="/evaluations", tags=["evaluations"])
compare_router = APIRouter(prefix="/compare", tags=["comparison"])
failures_router = APIRouter(prefix="/failures", tags=["failures"])
recommendations_router = APIRouter(prefix="/recommendations", tags=["recommendations"])
reports_router = APIRouter(prefix="/reports", tags=["reports"])
documents_router = APIRouter(prefix="/documents", tags=["rag"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# experiments
# ---------------------------------------------------------------------------
@experiments_router.get("", summary="List experiments")
def list_experiments(
    db: DbSession,
    page: PageParams,
    dataset_id: str | None = Query(None),
    search: str | None = Query(None),
) -> dict[str, Any]:
    service = ExperimentService(db)
    experiments, total = service.list(
        limit=page.limit, offset=page.offset, dataset_id=dataset_id, search=search
    )
    return {
        "items": [ExperimentRead(**service.to_read_dict(e)) for e in experiments],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@experiments_router.post("", response_model=ExperimentRead, status_code=201, summary="Create an experiment")
def create_experiment(payload: ExperimentCreate, db: DbSession) -> ExperimentRead:
    service = ExperimentService(db)
    return ExperimentRead(**service.to_read_dict(service.create(payload)))


@experiments_router.get("/{experiment_id}", response_model=ExperimentRead, summary="Get an experiment")
def get_experiment(experiment_id: str, db: DbSession) -> ExperimentRead:
    service = ExperimentService(db)
    return ExperimentRead(**service.to_read_dict(service.get(experiment_id)))


@experiments_router.delete("/{experiment_id}", response_model=Acknowledgement, summary="Delete an experiment")
def delete_experiment(experiment_id: str, db: DbSession) -> Acknowledgement:
    ExperimentService(db).delete(experiment_id)
    return Acknowledgement(message="Experiment deleted.", id=experiment_id)


@experiments_router.get("/{experiment_id}/runs", summary="List runs for an experiment")
def experiment_runs(experiment_id: str, db: DbSession) -> dict[str, Any]:
    service = EvaluationService(db)
    runs = ExperimentService(db).runs_for(experiment_id)
    return {"items": [EvaluationRunRead(**service.enrich_run(r)) for r in runs], "total": len(runs)}


@experiments_router.post("/{experiment_id}/improve", summary="Create a follow-up experiment")
def create_followup(
    experiment_id: str,
    payload: ImprovementRequest,
    background: BackgroundTasks,
    db: DbSession,
) -> dict[str, Any]:
    service = ImprovementService(db)
    followup, run, context = service.create_followup(experiment_id, payload)
    db.commit()
    if run is not None:
        background.add_task(execute_run, run.id)
    experiment_service = ExperimentService(db)
    return {
        "experiment": ExperimentRead(**experiment_service.to_read_dict(followup)).model_dump(),
        "run_id": run.id if run else None,
        **context,
    }


@experiments_router.get("/{experiment_id}/outcome", summary="Before/after outcome for a follow-up")
def experiment_outcome(experiment_id: str, db: DbSession) -> dict[str, Any]:
    return ImprovementService(db).outcome(experiment_id)


# ---------------------------------------------------------------------------
# evaluations
# ---------------------------------------------------------------------------
@evaluations_router.post("/run", response_model=EvaluationRunRead, status_code=202, summary="Start an evaluation run")
def run_evaluation(
    payload: RunEvaluationRequest, background: BackgroundTasks, db: DbSession
) -> EvaluationRunRead:
    service = EvaluationService(db)
    run = service.create_run(payload)
    payload_run_id = run.id
    enriched = service.enrich_run(run)
    db.commit()  # the background task opens its own session
    background.add_task(execute_run, payload_run_id)
    return EvaluationRunRead(**enriched)


@evaluations_router.get("", summary="List evaluation runs")
def list_runs(
    db: DbSession,
    page: PageParams,
    experiment_id: str | None = Query(None),
    status: str | None = Query(None),
) -> dict[str, Any]:
    service = EvaluationService(db)
    runs, total = service.list_runs(
        limit=page.limit, offset=page.offset, experiment_id=experiment_id, status=status
    )
    return {
        "items": [EvaluationRunRead(**service.enrich_run(r)) for r in runs],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@evaluations_router.get("/{run_id}", response_model=EvaluationRunRead, summary="Get run status")
def get_run(run_id: str, db: DbSession) -> EvaluationRunRead:
    service = EvaluationService(db)
    return EvaluationRunRead(**service.enrich_run(service.get_run(run_id)))


@evaluations_router.get("/{run_id}/results", summary="List run results")
def run_results(
    run_id: str,
    db: DbSession,
    page: PageParams,
    status: str | None = Query(None),
    failed_only: bool = Query(False),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    search: str | None = Query(None),
) -> dict[str, Any]:
    service = EvaluationService(db)
    results, total = service.results(
        run_id,
        limit=page.limit,
        offset=page.offset,
        status=status,
        failed_only=failed_only,
        model=model,
        provider=provider,
        search=search,
    )
    return {
        "items": [EvaluationResultRead.model_validate(r) for r in results],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@evaluations_router.get("/results/{result_id}", response_model=EvaluationResultRead, summary="Get one result")
def get_result(result_id: str, db: DbSession) -> EvaluationResultRead:
    from app.core.exceptions import NotFoundError
    from app.models.experiment import EvaluationResult

    result = db.get(EvaluationResult, result_id)
    if result is None:
        raise NotFoundError(f"Result '{result_id}' was not found.")
    return EvaluationResultRead.model_validate(result)


@evaluations_router.post("/{run_id}/retry", response_model=EvaluationRunRead, status_code=202, summary="Re-run errored cases")
def retry_run(run_id: str, background: BackgroundTasks, db: DbSession) -> EvaluationRunRead:
    """Re-run only the cases that failed at the provider (quota, timeout, network).

    A new run is created rather than mutating the original, so the original
    remains an accurate record of what happened.
    """
    service = EvaluationService(db)
    run = service.get_run(run_id)
    errored, _ = service.results(run_id, status="error")
    case_ids = sorted({r.test_case_id for r in errored})
    if not case_ids:
        raise ValidationFailedError("This run has no errored cases to retry.")
    new_run = service.create_run(
        RunEvaluationRequest(experiment_id=run.experiment_id, case_ids=case_ids)
    )
    enriched = service.enrich_run(new_run)
    db.commit()
    background.add_task(execute_run, new_run.id)
    return EvaluationRunRead(**enriched)


@evaluations_router.get("/{run_id}/improvement-suggestions", summary="Aggregated suggestions from diagnoses")
def improvement_suggestions(run_id: str, db: DbSession) -> dict[str, Any]:
    return ImprovementService(db).suggestions_for_run(run_id)


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------
@compare_router.post("", summary="Compare evaluation runs")
def compare_runs(payload: ComparisonRequest, db: DbSession) -> dict[str, Any]:
    return ComparisonService(db).compare_runs(
        payload.run_ids, baseline_run_id=payload.baseline_run_id, metrics=payload.metrics
    )


@compare_router.get("/models/{run_id}", summary="Compare models within one run")
def compare_models(run_id: str, db: DbSession) -> dict[str, Any]:
    return ComparisonService(db).compare_models(run_id)


@compare_router.get("/models/{run_id}/significance", summary="Pairwise significance testing across models within one run")
def compare_models_significance(run_id: str, db: DbSession, metric: str = Query("correctness")) -> dict[str, Any]:
    return ComparisonService(db).compare_models_significance(run_id, metric=metric)


@compare_router.get("/improvement", summary="Before/after comparison between two runs")
def improvement(baseline_run_id: str, followup_run_id: str, db: DbSession) -> dict[str, Any]:
    return ComparisonService(db).improvement_summary(baseline_run_id, followup_run_id)


# ---------------------------------------------------------------------------
# failures + diagnosis
# ---------------------------------------------------------------------------
@failures_router.get("", summary="List failures")
def list_failures(
    db: DbSession,
    page: PageParams,
    run_id: str | None = Query(None),
    experiment_id: str | None = Query(None),
    failure_type: str | None = Query(None),
    severity: str | None = Query(None),
    provider: str | None = Query(None),
    model: str | None = Query(None),
    diagnosed: bool | None = Query(None),
) -> dict[str, Any]:
    service = DiagnosisService(db)
    failures, total = service.list_failures(
        limit=page.limit,
        offset=page.offset,
        run_id=run_id,
        experiment_id=experiment_id,
        failure_type=failure_type,
        severity=severity,
        provider=provider,
        model=model,
        diagnosed=diagnosed,
    )
    return {
        "items": [_failure_block(f) for f in failures],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@failures_router.get("/distribution", summary="Failure type distribution")
def failure_distribution(db: DbSession, run_id: str | None = Query(None)) -> dict[str, Any]:
    return {"items": DiagnosisService(db).distribution(run_id)}


@failures_router.get("/{failure_id}", summary="Get one failure with full evidence")
def get_failure(failure_id: str, db: DbSession) -> dict[str, Any]:
    return _failure_block(DiagnosisService(db).get_failure(failure_id), full=True)


@failures_router.post("/{failure_id}/diagnose", summary="Run AI diagnosis on a failure")
async def diagnose_failure(
    failure_id: str, payload: DiagnoseRequest, db: DbSession
) -> dict[str, Any]:
    failure = await DiagnosisService(db).diagnose(failure_id, payload)
    return _failure_block(failure, full=True)


# ---------------------------------------------------------------------------
# recommendations
# ---------------------------------------------------------------------------
@recommendations_router.post("", response_model=RecommendationRead, status_code=201, summary="Generate a model recommendation")
def create_recommendation(payload: RecommendationRequest, db: DbSession) -> RecommendationRead:
    return RecommendationRead.model_validate(RecommendationService(db).build(payload))


@recommendations_router.get("", summary="List recommendations")
def list_recommendations(db: DbSession) -> dict[str, Any]:
    items = RecommendationService(db).list()
    return {"items": [RecommendationRead.model_validate(r) for r in items], "total": len(items)}


@recommendations_router.get("/{recommendation_id}", response_model=RecommendationRead, summary="Get a recommendation")
def get_recommendation(recommendation_id: str, db: DbSession) -> RecommendationRead:
    return RecommendationRead.model_validate(RecommendationService(db).get(recommendation_id))


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------
@reports_router.post("", response_model=ReportRead, status_code=201, summary="Generate a report")
def create_report(payload: ReportRequest, db: DbSession) -> ReportRead:
    return ReportRead.model_validate(ReportService(db).generate(payload))


@reports_router.get("", summary="List reports")
def list_reports(db: DbSession) -> dict[str, Any]:
    items = ReportService(db).list()
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "kind": r.kind,
                "run_id": r.run_id,
                "experiment_id": r.experiment_id,
                "baseline_run_id": r.baseline_run_id,
                "created_at": r.created_at,
            }
            for r in items
        ],
        "total": len(items),
    }


@reports_router.get("/{report_id}", response_model=ReportRead, summary="Get a report")
def get_report(report_id: str, db: DbSession) -> ReportRead:
    return ReportRead.model_validate(ReportService(db).get(report_id))


@reports_router.delete("/{report_id}", response_model=Acknowledgement, summary="Delete a report")
def delete_report(report_id: str, db: DbSession) -> Acknowledgement:
    ReportService(db).delete(report_id)
    return Acknowledgement(message="Report deleted.", id=report_id)


@reports_router.get("/{report_id}/export", summary="Export a report as JSON or CSV")
def export_report(report_id: str, db: DbSession, format: str = Query("json", pattern="^(json|csv)$")) -> Response:
    service = ReportService(db)
    report = service.get(report_id)
    if format == "csv":
        return Response(
            content=service.export_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{report.id}.csv"'},
        )
    return Response(
        content=service.export_json(report),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{report.id}.json"'},
    )


# ---------------------------------------------------------------------------
# documents / RAG
# ---------------------------------------------------------------------------
@documents_router.get("", summary="List documents")
def list_documents(db: DbSession, collection: str | None = Query(None)) -> dict[str, Any]:
    service = RagService(db)
    documents = service.list(collection=collection)
    return {
        "items": [DocumentRead.model_validate(d) for d in documents],
        "total": len(documents),
        "collections": service.collections(),
    }


@documents_router.post("/upload", response_model=DocumentRead, status_code=201, summary="Upload a document")
async def upload_document(
    db: DbSession,
    file: UploadFile = File(..., description="PDF, TXT or Markdown"),
    collection: str = Form("default"),
) -> DocumentRead:
    content = await file.read()
    document = RagService(db).store_upload(
        filename=file.filename or "document",
        content=content,
        content_type=file.content_type,
        collection=collection,
    )
    return DocumentRead.model_validate(document)


@documents_router.post("/index", summary="Chunk, embed and index documents")
async def index_documents(payload: DocumentIndexRequest, db: DbSession) -> dict[str, Any]:
    return await RagService(db).index(
        payload.document_ids,
        collection=payload.collection,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        embedding_backend=payload.embedding_backend,
    )


@documents_router.post("/preview", summary="Preview retrieval for a query")
async def preview_retrieval(payload: RetrievalPreviewRequest, db: DbSession) -> dict[str, Any]:
    return await RagService(db).preview(
        query=payload.query,
        collection=payload.collection,
        top_k=payload.top_k,
        strategy=payload.strategy,
    )


@documents_router.delete("/{document_id}", response_model=Acknowledgement, summary="Delete a document")
def delete_document(document_id: str, db: DbSession) -> Acknowledgement:
    RagService(db).delete(document_id)
    return Acknowledgement(message="Document deleted.", id=document_id)


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------
@dashboard_router.get("", response_model=DashboardResponse, summary="Dashboard aggregates")
def dashboard(db: DbSession) -> DashboardResponse:
    return DashboardResponse(**DashboardService(db).build())


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _failure_block(failure, *, full: bool = False) -> dict[str, Any]:
    result = failure.result
    block = {
        **FailureRead.model_validate(failure).model_dump(),
        "provider": result.provider if result else None,
        "model": result.model if result else None,
        "model_label": result.model_label if result else None,
        "question": (result.question if result else "")[: (None if full else 240)],
        "status": result.status if result else None,
        "latency_ms": result.latency_ms if result else None,
        "composite_score": result.composite_score if result else None,
        "scores": result.metric_map if result else {},
    }
    if full and result is not None:
        block["result"] = EvaluationResultRead.model_validate(result).model_dump()
    return block
