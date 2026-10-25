"""Aggregate API router."""

from fastapi import APIRouter

from app.api.routes.calibration import calibration_router
from app.api.routes.datasets import benchmark_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.evaluations import (
    compare_router,
    dashboard_router,
    documents_router,
    evaluations_router,
    experiments_router,
    failures_router,
    recommendations_router,
    reports_router,
)
from app.api.routes.health import router as health_router
from app.api.routes.providers import router as providers_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(dashboard_router)
api_router.include_router(datasets_router)
api_router.include_router(benchmark_router)
api_router.include_router(experiments_router)
api_router.include_router(evaluations_router)
api_router.include_router(compare_router)
api_router.include_router(failures_router)
api_router.include_router(recommendations_router)
api_router.include_router(reports_router)
api_router.include_router(documents_router)
api_router.include_router(providers_router)
api_router.include_router(calibration_router)
