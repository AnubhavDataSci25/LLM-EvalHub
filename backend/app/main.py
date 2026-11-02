"""LLM-EvalHub API application."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.api.routes.health import health as health_route
from app.api.routes.health import prometheus_metrics
from app.api.routes.health import ready as ready_route
from app.core.config import settings
from app.core.exceptions import EvalHubError
from app.core.logging import (
    configure_logging,
    get_logger,
    request_id_ctx,
    workspace_id_ctx,
)
from app.core.metrics import metrics_collector
from app.db.init_db import init_db
from app.db.session import get_db

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """
**LLM-EvalHub** — an evaluation-first platform for benchmarking LLM and RAG
applications, diagnosing failures and proving whether a change actually improved
the system.

The product loop this API supports:

`Evaluate → Compare → Diagnose → Recommend → Improve → Re-evaluate`

Notes for API consumers:

* Provider API keys live server-side only and are never returned by any endpoint.
* Metrics are labelled `deterministic`, `llm_judge`, `ragas` or `performance`.
  A metric whose required input is missing is returned as **unavailable**, never
  as a zero score.
* Recommendations are scoped to the evaluation data that produced them and are
  not a general model ranking.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    settings.ensure_dirs()
    try:
        from app.services.jobs import JobService

        recovered = JobService.recover_interrupted_jobs()
        if recovered:
            logger.info("Recovered %s interrupted jobs/runs on startup", recovered)
    except Exception as exc:
        logger.warning("Failed recovering interrupted jobs on startup: %s", exc)
    logger.info(
        "%s starting (env=%s, db=%s, job_backend=%s)",
        settings.app_name,
        settings.app_env,
        "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
        settings.effective_job_backend,
    )
    try:
        from app.db.session import SessionLocal
        from app.services.audit_service import AuditService

        with SessionLocal() as session:
            eval_check = AuditService(session).check_default_evaluator()
            if eval_check.get("warning"):
                alt_msg = ""
                if eval_check.get("suggested_alternative"):
                    alt = eval_check["suggested_alternative"]
                    alt_msg = f" Suggested alternative: {alt['provider']}/{alt['model_id']}."
                logger.warning("[Startup] %s%s", eval_check["warning"], alt_msg)
    except Exception as e:
        logger.debug("Failed startup default evaluator check: %s", e)
    yield
    logger.info("%s shutting down", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Strict CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
)


@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    # 1. Correlation IDs & Context Setup
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"
    wks_id = request.headers.get("X-Workspace-Id") or request.query_params.get("workspace_id") or "-"
    request_id_ctx.set(req_id)
    workspace_id_ctx.set(wks_id)

    # 2. Request Payload Size Validation
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_upload_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": f"Request size exceeds limit of {settings.max_upload_bytes} bytes.",
                            "details": None,
                        }
                    },
                )
        except ValueError:
            pass

    # 3. Request Execution & Performance Timing
    started = time.perf_counter()
    response = await call_next(request)
    duration_s = time.perf_counter() - started
    elapsed_ms = duration_s * 1000

    # 4. Tracing Headers
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"

    # 5. Security Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # API routes get strict CSP frame-ancestors restriction
    if request.url.path.startswith(settings.api_prefix):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none';"

    # 6. Operational Metrics Tracking
    metrics_collector.record_request(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
        duration_seconds=duration_s,
    )

    if elapsed_ms > 3000:
        logger.info("slow request %s %s took %.0f ms", request.method, request.url.path, elapsed_ms)

    return response


# --- consistent error payloads --------------------------------------------
@app.exception_handler(EvalHubError)
async def evalhub_error_handler(_: Request, exc: EvalHubError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_failed",
                "message": "The request payload failed validation.",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "details": None,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred. Check the server logs for details.",
                "details": str(exc)[:300] if settings.app_debug else None,
            }
        },
    )


# Mount main API router
app.include_router(api_router, prefix=settings.api_prefix)


# Root level endpoints for orchestrator & liveness checks
@app.get("/health", include_in_schema=False)
def root_health():
    return health_route()


@app.get("/ready", include_in_schema=False)
def root_ready(db: Session = Depends(get_db)):
    return ready_route(db)


@app.get("/metrics", include_in_schema=False)
def root_metrics() -> Response:
    return prometheus_metrics()


@app.get("/", tags=["meta"], summary="Service banner")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "api": settings.api_prefix,
    }
