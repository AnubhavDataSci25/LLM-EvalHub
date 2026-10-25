"""LLM-EvalHub API application."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import EvalHubError
from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_db

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
    logger.info(
        "%s starting (env=%s, db=%s)",
        settings.app_name,
        settings.app_env,
        "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
    )
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
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
                "details": exc.errors(),
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


app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["meta"], summary="Service banner")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "api": settings.api_prefix,
    }
