"""Service layer for Reasoning Arena: Chess benchmarks and interactive games."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.base import new_id
from app.evaluation.games.engine import get_chess_engine
from app.models.game import GameMove, GameRun
from app.providers.registry import get_provider
from app.schemas.arena import (
    ArenaChessRunCreate,
    ArenaChessStatus,
    ArenaChessSummary,
    ArenaDryRunEstimate,
)
from app.workflows.game_graph import ChessGameGraph, GameWorkflowState

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ArenaService:
    """Manages Reasoning Arena runs, dry runs, and persistence."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_status(self) -> ArenaChessStatus:
        """Inspect host environment for Stockfish engine availability."""
        engine = get_chess_engine()
        return ArenaChessStatus(
            stockfish_available=engine.is_available,
            stockfish_path=engine._resolved_path,
            stockfish_version=engine.get_version(),
            unavailable_reason=engine.unavailable_reason,
            default_config={
                "depth": settings.stockfish_depth,
                "skill_level": settings.stockfish_skill_level,
                "max_moves": settings.game_max_moves,
                "max_retries": settings.game_max_retries,
                "blunder_threshold_cp": settings.blunder_threshold_cp,
            },
        )

    def estimate_dry_run(self, payload: ArenaChessRunCreate) -> ArenaDryRunEstimate:
        """Compute strict upper bounds on provider API calls before starting."""
        if payload.task_type == "game":
            estimated_calls = payload.max_moves * (1 + payload.max_retries)
            upper_bound_tokens = estimated_calls * 650
            msg = (
                f"Full game up to {payload.max_moves} model moves with {payload.max_retries} max retry/move. "
                f"Upper bound is {estimated_calls} provider calls."
            )
        elif payload.task_type == "puzzle_suite":
            estimated_calls = 76
            upper_bound_tokens = estimated_calls * 450
            msg = f"Puzzle suite benchmark across {estimated_calls} verified positions (1 call per position)."
        else:
            estimated_calls = 50
            upper_bound_tokens = estimated_calls * 350
            msg = f"Legal moves compliance test on {estimated_calls} positions."

        return ArenaDryRunEstimate(
            task_type=payload.task_type,
            model_id=payload.model_id,
            provider_key=payload.provider_key,
            estimated_calls=estimated_calls,
            max_moves=payload.max_moves,
            max_retries_per_move=payload.max_retries,
            estimated_tokens_upper_bound=upper_bound_tokens,
            message=msg,
        )

    async def create_and_execute_game(
        self,
        payload: ArenaChessRunCreate,
        workspace_id: str = "wks_default",
    ) -> GameRun:
        """Create a new game run, execute the LangGraph workflow, and persist results."""
        run = GameRun(
            id=new_id("grun"),
            workspace_id=workspace_id,
            game_type="chess",
            task_type=payload.task_type,
            model_id=payload.model_id,
            provider_key=payload.provider_key,
            status="running",
            config=payload.model_dump(),
            summary={},
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        # Execute game through LangGraph
        try:
            provider = get_provider(payload.provider_key)
            engine = get_chess_engine()

            async def persist_move_cb(move_dict: dict[str, Any]) -> None:
                move_obj = GameMove(
                    id=new_id("gmove"),
                    game_run_id=run.id,
                    ply=move_dict["ply"],
                    turn=move_dict["turn"],
                    fen_before=move_dict["fen_before"],
                    fen_after=move_dict.get("fen_after"),
                    raw_model_output=move_dict.get("raw_model_output"),
                    parsed_move=move_dict.get("parsed_move"),
                    is_legal=move_dict.get("is_legal", False),
                    is_parseable=move_dict.get("is_parseable", False),
                    retry_count=move_dict.get("retry_count", 0),
                    engine_eval_before=move_dict.get("engine_eval_before"),
                    engine_eval_after=move_dict.get("engine_eval_after"),
                    centipawn_loss=move_dict.get("centipawn_loss"),
                    is_blunder=move_dict.get("is_blunder", False),
                    latency_ms=move_dict.get("latency_ms"),
                    commentary=move_dict.get("commentary"),
                )
                self.db.add(move_obj)
                self.db.commit()

            runner = ChessGameGraph(
                provider=provider,
                engine=engine,
                persist_move=persist_move_cb,
            )

            init_state: GameWorkflowState = {
                "run_id": run.id,
                "workspace_id": workspace_id,
                "model_id": payload.model_id,
                "provider_key": payload.provider_key,
                "model_color": payload.model_color,
                "max_moves": payload.max_moves,
                "max_retries": payload.max_retries,
                "prompt_variant": payload.prompt_variant,
                "think_step_by_step": payload.think_step_by_step,
                "temperature": payload.temperature,
                "current_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "ply": 0,
                "moves": [],
                "centipawn_losses": [],
                "blunders_count": 0,
                "total_model_attempts": 0,
                "legal_model_moves": 0,
                "parseable_model_moves": 0,
                "retries_used": 0,
                "status": "running",
            }

            final_state = await runner.run(init_state)

            run.status = final_state.get("status", "completed")
            run.summary = final_state.get("summary", {})
            run.completed_at = _utcnow()
            self.db.commit()
            self.db.refresh(run)

        except Exception as exc:
            logger.exception("Failed executing arena game %s", run.id)
            run.status = "failed"
            run.error_message = str(exc)[:500]
            run.completed_at = _utcnow()
            self.db.commit()
            self.db.refresh(run)

        return run

    def get_run(self, run_id: str) -> GameRun:
        run = self.db.execute(
            select(GameRun)
            .where(GameRun.id == run_id)
            .options(selectinload(GameRun.moves))
        ).scalar_one_or_none()
        if not run:
            raise NotFoundError(f"Arena run '{run_id}' not found")
        return run

    def list_runs(self, workspace_id: str = "wks_default", limit: int = 50) -> list[GameRun]:
        return list(
            self.db.execute(
                select(GameRun)
                .where(GameRun.workspace_id == workspace_id)
                .order_by(GameRun.created_at.desc())
                .limit(limit)
                .options(selectinload(GameRun.moves))
            ).scalars().all()
        )

    def get_summary(self, workspace_id: str = "wks_default") -> ArenaChessSummary:
        runs = list(
            self.db.execute(
                select(GameRun).where(GameRun.workspace_id == workspace_id)
            ).scalars().all()
        )

        total_runs = len(runs)
        completed = [r for r in runs if r.status == "completed"]
        completed_games = len(completed)

        model_wins = sum(1 for r in completed if (r.summary or {}).get("outcome") == "model_win")
        engine_wins = sum(1 for r in completed if (r.summary or {}).get("outcome") == "engine_win")
        draws = sum(1 for r in completed if (r.summary or {}).get("outcome") == "draw")
        forfeits = sum(1 for r in completed if (r.summary or {}).get("outcome") == "model_forfeit_illegal")

        legal_rates = [
            r.summary.get("legal_move_rate")
            for r in completed
            if r.summary and r.summary.get("legal_move_rate") is not None
        ]
        overall_legal = round(sum(legal_rates) / len(legal_rates), 4) if legal_rates else None

        models = sorted({r.model_id for r in runs if r.model_id})

        return ArenaChessSummary(
            total_runs=total_runs,
            completed_games=completed_games,
            model_wins=model_wins,
            engine_wins=engine_wins,
            draws=draws,
            forfeits=forfeits,
            overall_legal_move_rate=overall_legal,
            models_evaluated=models,
        )
