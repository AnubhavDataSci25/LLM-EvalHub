"""API routes for human labelling, agreement calculations, and judge calibration runs."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.calibration import (
    CalibrationRunRead,
    CalibrationRunRequest,
    HumanLabelRead,
    LabelUpsertRequest,
    QueueItemRead,
    ReliabilityResponse,
)
from app.services.calibration_service import CalibrationService

calibration_router = APIRouter(prefix="/calibration", tags=["calibration"])


@calibration_router.get("/queue", response_model=list[QueueItemRead], summary="Fetch blind labelling queue")
def get_labelling_queue(
    db: DbSession,
    run_id: str = Query(..., description="Evaluation run ID to sample from"),
    metric: str = Query("correctness", description="Metric to label: correctness, faithfulness, or answer_relevance"),
    limit: int = Query(30, ge=1, le=100, description="Maximum number of cases to return"),
) -> list[QueueItemRead]:
    service = CalibrationService(db)
    items = service.list_unlabelled(run_id=run_id, metric=metric, limit=limit)
    return [QueueItemRead(**i) for i in items]


@calibration_router.post("/labels", response_model=HumanLabelRead, summary="Upsert human label")
def upsert_label(
    db: DbSession,
    payload: LabelUpsertRequest,
) -> HumanLabelRead:
    service = CalibrationService(db)
    label = service.label(
        result_id=payload.result_id,
        metric=payload.metric,
        label=payload.label,
        annotator=payload.annotator,
        note=payload.note,
    )
    return HumanLabelRead.model_validate(label)


@calibration_router.get("/labels", response_model=list[HumanLabelRead], summary="List human labels")
def list_labels(
    db: DbSession,
    run_id: str | None = Query(None, description="Filter by evaluation run"),
    metric: str | None = Query(None, description="Filter by metric"),
) -> list[HumanLabelRead]:
    service = CalibrationService(db)
    labels = service.list_labels(run_id=run_id, metric=metric)
    return [HumanLabelRead.model_validate(lbl) for lbl in labels]


@calibration_router.post("/run", response_model=CalibrationRunRead, summary="Execute judge calibration and bias probes")
async def run_calibration(
    db: DbSession,
    payload: CalibrationRunRequest,
) -> CalibrationRunRead:
    service = CalibrationService(db)
    cal_run = await service.calibrate(
        run_id=payload.run_id,
        dataset_id=payload.dataset_id,
        metric=payload.metric,
        judge_provider=payload.judge_provider,
        judge_model=payload.judge_model,
        run_probes=payload.run_probes,
    )
    return CalibrationRunRead.model_validate(cal_run)


@calibration_router.get("/runs", response_model=list[CalibrationRunRead], summary="List calibration runs")
def list_calibration_runs(
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
) -> list[CalibrationRunRead]:
    service = CalibrationService(db)
    runs = service.list_runs(limit=limit)
    return [CalibrationRunRead.model_validate(r) for r in runs]


@calibration_router.get("/runs/{run_id}", response_model=CalibrationRunRead, summary="Get calibration run detail")
def get_calibration_run(
    db: DbSession,
    run_id: str,
) -> CalibrationRunRead:
    service = CalibrationService(db)
    cal_run = service.get_run(run_id)
    return CalibrationRunRead.model_validate(cal_run)


@calibration_router.get("/reliability", response_model=ReliabilityResponse, summary="Get judge reliability summary")
def get_reliability(
    db: DbSession,
    provider: str = Query(..., description="Judge provider key"),
    model: str = Query(..., description="Judge model name"),
    metric: str = Query("correctness", description="Metric to inspect"),
) -> ReliabilityResponse:
    service = CalibrationService(db)
    rel = service.get_reliability(judge_provider=provider, judge_model=model, metric=metric)
    if rel is None:
        return ReliabilityResponse(
            calibrated=False,
            status="uncalibrated",
            judge_provider=provider,
            judge_model=model,
            metric=metric,
            kappa=None,
            n_labels=0,
            warnings=["No completed calibration run found for this judge and metric."],
        )
    return ReliabilityResponse(**rel)
