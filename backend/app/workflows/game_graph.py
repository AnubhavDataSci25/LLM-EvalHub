"""LangGraph workflow for interactive Reasoning Arena game execution.

Orchestrates game turns between an LLM and an opponent engine (Stockfish or Stub),
enforcing bounded moves, retry policies for illegal moves, move validation,
centipawn loss tracking, and reproducible persistence.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

import chess
from langgraph.graph import END, START, StateGraph

from app.core.concurrency import with_retries
from app.core.logging import get_logger
from app.evaluation.games.chess_env import ChessEnvironment
from app.evaluation.games.engine import ChessEngineAdapter, get_chess_engine
from app.providers.base import LLMProvider

logger = get_logger(__name__)

PersistMoveCallback = Callable[[dict[str, Any]], Awaitable[None]]


class GameWorkflowState(TypedDict, total=False):
    """State threaded through the LangGraph game workflow."""

    # identity
    run_id: str
    workspace_id: str
    model_id: str
    provider_key: str
    model_color: str  # "white" | "black"
    max_moves: int
    max_retries: int
    prompt_variant: str
    think_step_by_step: bool
    temperature: float

    # game board state
    current_fen: str
    ply: int
    is_terminal: bool
    outcome: str | None  # "model_win" | "engine_win" | "draw" | "model_forfeit_illegal"
    termination_reason: str | None
    error_message: str | None

    # retry handling for current ply
    retry_count: int
    retry_in_progress: bool
    retry_feedback: str | None

    # move history and metrics tracking
    moves: list[dict[str, Any]]
    total_model_attempts: int
    legal_model_moves: int
    parseable_model_moves: int
    retries_used: int
    blunders_count: int
    centipawn_losses: list[float]

    # transient turn variables
    last_prompt: str | None
    last_raw_response: str | None
    last_latency_ms: float | None
    last_action: dict[str, Any] | None

    summary: dict[str, Any]
    status: str


class ChessGameGraph:
    """Compiled LangGraph game loop runner."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        engine: ChessEngineAdapter | None = None,
        persist_move: PersistMoveCallback | None = None,
    ) -> None:
        self.provider = provider
        self.engine = engine or get_chess_engine()
        self.persist_move = persist_move
        self.env = ChessEnvironment(engine_adapter=self.engine)
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(GameWorkflowState)

        workflow.add_node("check_terminal", self.check_terminal)
        workflow.add_node("model_generate", self.model_generate)
        workflow.add_node("parse_and_validate", self.parse_and_validate)
        workflow.add_node("engine_turn", self.engine_turn)
        workflow.add_node("finalize", self.finalize)

        workflow.add_edge(START, "check_terminal")

        # Routing from check_terminal
        workflow.add_conditional_edges(
            "check_terminal",
            self._route_after_check,
            {
                "model_turn": "model_generate",
                "engine_turn": "engine_turn",
                "finalize": "finalize",
            },
        )

        workflow.add_edge("model_generate", "parse_and_validate")

        # Routing after validation: retry, advance to terminal check, or forfeit to finalize
        workflow.add_conditional_edges(
            "parse_and_validate",
            self._route_after_validate,
            {
                "retry": "model_generate",
                "next_turn": "check_terminal",
                "forfeit": "finalize",
            },
        )

        workflow.add_edge("engine_turn", "check_terminal")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _route_after_check(self, state: GameWorkflowState) -> str:
        if state.get("is_terminal"):
            return "finalize"

        board = chess.Board(state["current_fen"])
        is_model_white = state.get("model_color", "white").lower() == "white"
        is_white_turn = board.turn == chess.WHITE

        if (is_model_white and is_white_turn) or (not is_model_white and not is_white_turn):
            return "model_turn"
        return "engine_turn"

    def _route_after_validate(self, state: GameWorkflowState) -> str:
        if state.get("retry_in_progress"):
            return "retry"
        if state.get("is_terminal"):
            return "forfeit"
        return "next_turn"

    async def check_terminal(self, state: GameWorkflowState) -> dict[str, Any]:
        fen = state.get("current_fen", chess.STARTING_FEN)
        board = chess.Board(fen)
        ply = state.get("ply", 0)
        max_moves = state.get("max_moves", 60)
        max_plies = max_moves * 2

        if board.is_checkmate():
            # Winner is the one who made the last move
            is_model_white = state.get("model_color", "white").lower() == "white"
            winner_is_white = board.turn == chess.BLACK
            model_won = (winner_is_white and is_model_white) or (not winner_is_white and not is_model_white)
            return {
                "is_terminal": True,
                "outcome": "model_win" if model_won else "engine_win",
                "termination_reason": "checkmate",
            }

        if board.is_stalemate():
            return {
                "is_terminal": True,
                "outcome": "draw",
                "termination_reason": "stalemate",
            }

        if board.is_insufficient_material() or board.can_claim_threefold_repetition() or board.can_claim_fifty_moves():
            return {
                "is_terminal": True,
                "outcome": "draw",
                "termination_reason": "draw_by_rules",
            }

        if ply >= max_plies:
            return {
                "is_terminal": True,
                "outcome": "draw",
                "termination_reason": "max_moves_reached",
            }

        return {"is_terminal": False}

    async def model_generate(self, state: GameWorkflowState) -> dict[str, Any]:
        self.env.load_position(state["current_fen"])
        prompt = self.env.render_prompt(
            variant=state.get("prompt_variant", "fen_ascii"),
            think_step_by_step=state.get("think_step_by_step", False),
        )

        if state.get("retry_in_progress") and state.get("retry_feedback"):
            prompt += f"\n\nNOTICE: {state['retry_feedback']}\nPlease provide a valid, legal move."

        t0 = time.perf_counter()
        try:
            call_fn = lambda: self.provider.generate(  # noqa: E731
                prompt=prompt,
                model=state["model_id"],
                temperature=state.get("temperature", 0.0),
                max_tokens=512,
            )
            response = await with_retries(call_fn, attempts=2)
            answer_text = response.text if hasattr(response, "text") else str(response)
        except Exception as exc:
            logger.warning("Provider generation call failed: %s", exc)
            answer_text = ""

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "last_prompt": prompt,
            "last_raw_response": answer_text,
            "last_latency_ms": latency_ms,
            "total_model_attempts": state.get("total_model_attempts", 0) + 1,
        }

    async def parse_and_validate(self, state: GameWorkflowState) -> dict[str, Any]:
        self.env.load_position(state["current_fen"])
        raw_output = state.get("last_raw_response", "")
        action = self.env.parse_action(raw_output)

        ply = state.get("ply", 0) + 1
        turn_str = "white" if self.env.board.turn == chess.WHITE else "black"
        fen_before = state["current_fen"]
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 1)

        parseable_count = state.get("parseable_model_moves", 0)
        legal_count = state.get("legal_model_moves", 0)
        retries_used = state.get("retries_used", 0)

        if action.is_parseable:
            parseable_count += 1

        if not action.is_legal:
            if retry_count < max_retries:
                # Issue retry
                feedback = (
                    f"The move '{action.parsed}' is not legal for {turn_str} in this position ({action.error_reason})."
                    if action.is_parseable
                    else "Could not parse a chess move from your output."
                )
                return {
                    "retry_in_progress": True,
                    "retry_count": retry_count + 1,
                    "retries_used": retries_used + 1,
                    "retry_feedback": feedback,
                    "parseable_model_moves": parseable_count,
                }
            else:
                # Forfeited game due to repeated illegal / unparseable move
                move_record = {
                    "ply": ply,
                    "turn": turn_str,
                    "fen_before": fen_before,
                    "fen_after": None,
                    "raw_model_output": raw_output,
                    "parsed_move": action.parsed,
                    "is_legal": False,
                    "is_parseable": action.is_parseable,
                    "retry_count": retry_count,
                    "engine_eval_before": None,
                    "engine_eval_after": None,
                    "centipawn_loss": None,
                    "is_blunder": False,
                    "latency_ms": state.get("last_latency_ms"),
                    "commentary": f"Forfeited: illegal move after {retry_count} retries ({action.error_reason})",
                }
                if self.persist_move:
                    await self.persist_move(move_record)

                moves = list(state.get("moves", []))
                moves.append(move_record)
                return {
                    "retry_in_progress": False,
                    "is_terminal": True,
                    "outcome": "model_forfeit_illegal",
                    "termination_reason": "illegal_move_forfeit",
                    "error_message": f"Illegal move: {action.error_reason}",
                    "ply": ply,
                    "moves": moves,
                    "parseable_model_moves": parseable_count,
                    "legal_model_moves": legal_count,
                }

        # Move is legal!
        legal_count += 1
        uci = action.metadata.get("uci")
        move_obj = chess.Move.from_uci(uci) if uci else None

        # Engine evaluation if available
        cp_loss: float | None = None
        is_blunder: bool = False
        eval_before: float | None = None
        eval_after: float | None = None

        if self.engine and self.engine.is_available and move_obj:
            try:
                analysis = self.engine.evaluate_move_sync(self.env.board, move_obj)
                cp_loss = analysis.get("centipawn_loss")
                is_blunder = analysis.get("is_blunder", False)
                eval_before = analysis.get("eval_before")
                eval_after = analysis.get("eval_after")
            except Exception as exc:
                logger.debug("Move analysis error: %s", exc)

        self.env.board.push(move_obj)
        fen_after = self.env.board.fen()

        move_record = {
            "ply": ply,
            "turn": turn_str,
            "fen_before": fen_before,
            "fen_after": fen_after,
            "raw_model_output": raw_output,
            "parsed_move": action.parsed,
            "is_legal": True,
            "is_parseable": True,
            "retry_count": retry_count,
            "engine_eval_before": eval_before,
            "engine_eval_after": eval_after,
            "centipawn_loss": cp_loss,
            "is_blunder": is_blunder,
            "latency_ms": state.get("last_latency_ms"),
            "commentary": f"Legal move {action.parsed}",
        }
        if self.persist_move:
            await self.persist_move(move_record)

        moves = list(state.get("moves", []))
        moves.append(move_record)

        losses = list(state.get("centipawn_losses", []))
        if cp_loss is not None:
            losses.append(cp_loss)

        blunders = state.get("blunders_count", 0) + (1 if is_blunder else 0)

        return {
            "current_fen": fen_after,
            "ply": ply,
            "retry_count": 0,
            "retry_in_progress": False,
            "retry_feedback": None,
            "moves": moves,
            "legal_model_moves": legal_count,
            "parseable_model_moves": parseable_count,
            "centipawn_losses": losses,
            "blunders_count": blunders,
        }

    async def engine_turn(self, state: GameWorkflowState) -> dict[str, Any]:
        self.env.load_position(state["current_fen"])
        ply = state.get("ply", 0) + 1
        turn_str = "white" if self.env.board.turn == chess.WHITE else "black"
        fen_before = state["current_fen"]

        engine_move = await self.engine.play_move(self.env.board)
        if not engine_move:
            # Fallback to first legal move if engine returns None
            moves = list(self.env.board.legal_moves)
            engine_move = moves[0] if moves else None

        if not engine_move:
            return {"is_terminal": True, "outcome": "draw", "termination_reason": "no_legal_moves"}

        san_str = self.env.board.san(engine_move)
        self.env.board.push(engine_move)
        fen_after = self.env.board.fen()

        move_record = {
            "ply": ply,
            "turn": turn_str,
            "fen_before": fen_before,
            "fen_after": fen_after,
            "raw_model_output": f"Engine played {san_str}",
            "parsed_move": san_str,
            "is_legal": True,
            "is_parseable": True,
            "retry_count": 0,
            "engine_eval_before": None,
            "engine_eval_after": None,
            "centipawn_loss": None,
            "is_blunder": False,
            "latency_ms": 10.0,
            "commentary": f"Opponent engine move {san_str}",
        }
        if self.persist_move:
            await self.persist_move(move_record)

        moves = list(state.get("moves", []))
        moves.append(move_record)

        return {
            "current_fen": fen_after,
            "ply": ply,
            "moves": moves,
        }

    async def finalize(self, state: GameWorkflowState) -> dict[str, Any]:
        total_attempts = max(1, state.get("total_model_attempts", 0))
        legal_moves = state.get("legal_model_moves", 0)
        parseable_moves = state.get("parseable_model_moves", 0)
        losses = state.get("centipawn_losses", [])
        blunders = state.get("blunders_count", 0)

        legal_move_rate = round(legal_moves / total_attempts, 4) if total_attempts else 0.0
        format_compliance_rate = round(parseable_moves / total_attempts, 4) if total_attempts else 0.0
        avg_loss = round(sum(losses) / len(losses), 2) if losses else None
        blunder_rate = round(blunders / legal_moves, 4) if legal_moves else None

        summary = {
            "outcome": state.get("outcome", "draw"),
            "termination_reason": state.get("termination_reason", "completed"),
            "total_plies": state.get("ply", 0),
            "model_moves_count": legal_moves,
            "model_attempts_count": total_attempts,
            "retries_used": state.get("retries_used", 0),
            "legal_move_rate": legal_move_rate,
            "format_compliance_rate": format_compliance_rate,
            "avg_centipawn_loss": avg_loss,
            "blunder_rate": blunder_rate,
            "stockfish_evaluated": bool(losses),
        }

        return {
            "status": "completed",
            "summary": summary,
        }

    async def run(self, initial_state: GameWorkflowState) -> GameWorkflowState:
        return await self.graph.ainvoke(initial_state)
