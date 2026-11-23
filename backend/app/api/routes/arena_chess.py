"""API routes for Reasoning Arena: Chess."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentWorkspaceContext
from app.schemas.arena import (
    ArenaChessRunCreate,
    ArenaChessStatus,
    ArenaChessSummary,
    ArenaDryRunEstimate,
    GameRunOut,
)
from app.services.arena_service import ArenaService

arena_chess_router = APIRouter(prefix="/arena/chess", tags=["arena-chess"])


@arena_chess_router.get("/status", response_model=ArenaChessStatus, summary="Get Stockfish and arena status")
def get_chess_status(ctx: CurrentWorkspaceContext) -> ArenaChessStatus:
    service = ArenaService(ctx.db)
    return service.get_status()


@arena_chess_router.get("/summary", response_model=ArenaChessSummary, summary="Get arena summary statistics")
def get_chess_summary(ctx: CurrentWorkspaceContext) -> ArenaChessSummary:
    service = ArenaService(ctx.db)
    return service.get_summary(workspace_id=ctx.workspace.id)


@arena_chess_router.post(
    "/dry-run",
    response_model=ArenaDryRunEstimate,
    summary="Estimate provider API calls and token bounds for a run",
)
def estimate_run_dry_run(
    ctx: CurrentWorkspaceContext,
    payload: ArenaChessRunCreate,
) -> ArenaDryRunEstimate:
    service = ArenaService(ctx.db)
    return service.estimate_dry_run(payload)


@arena_chess_router.post(
    "/runs",
    response_model=GameRunOut | ArenaDryRunEstimate,
    summary="Start an arena game run or dry-run",
)
async def create_chess_run(
    ctx: CurrentWorkspaceContext,
    payload: ArenaChessRunCreate,
) -> Any:
    service = ArenaService(ctx.db)
    if payload.dry_run:
        return service.estimate_dry_run(payload)
    return await service.create_and_execute_game(payload, workspace_id=ctx.workspace.id)


@arena_chess_router.get("/runs", response_model=list[GameRunOut], summary="List arena runs")
def list_chess_runs(
    ctx: CurrentWorkspaceContext,
    limit: int = Query(50, ge=1, le=100),
) -> list[GameRunOut]:
    service = ArenaService(ctx.db)
    return service.list_runs(workspace_id=ctx.workspace.id, limit=limit)


@arena_chess_router.get("/runs/{run_id}", response_model=GameRunOut, summary="Get arena run by ID")
def get_chess_run(
    ctx: CurrentWorkspaceContext,
    run_id: str,
) -> GameRunOut:
    service = ArenaService(ctx.db)
    return service.get_run(run_id)


@arena_chess_router.get("/runs/{run_id}/games", response_model=list[GameRunOut], summary="Get games for a run")
def get_chess_run_games(
    ctx: CurrentWorkspaceContext,
    run_id: str,
) -> list[GameRunOut]:
    service = ArenaService(ctx.db)
    run = service.get_run(run_id)
    return [run]


@arena_chess_router.get("/games/{game_id}", response_model=GameRunOut, summary="Get arena game details")
def get_chess_game(
    ctx: CurrentWorkspaceContext,
    game_id: str,
) -> GameRunOut:
    service = ArenaService(ctx.db)
    return service.get_run(game_id)
