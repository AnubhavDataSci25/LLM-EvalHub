"""Stockfish chess engine integration and reproducible evaluation.

Uses python-chess's engine protocol with fixed depth/nodes (not wall-clock time)
to ensure deterministic evaluations and opponent play. If Stockfish is not found,
engine-dependent metrics gracefully report as unavailable.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

import chess
import chess.engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MATE_SCORE_CAP = 10000  # Centipawn value assigned to checkmate


class ChessEngineAdapter:
    """Manages Stockfish UCI engine communication with async thread-pool isolation."""

    def __init__(
        self,
        binary_path: str | None = None,
        depth: int = 10,
        nodes: int | None = None,
        skill_level: int = 5,
    ) -> None:
        self.configured_path = binary_path or settings.stockfish_path
        self.depth = depth or settings.stockfish_depth
        self.nodes = nodes or settings.stockfish_nodes
        self.skill_level = skill_level if skill_level is not None else settings.stockfish_skill_level
        self._resolved_path: str | None = self._find_binary()
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = asyncio.Lock()

    def _find_binary(self) -> str | None:
        if self.configured_path and os.path.isfile(self.configured_path):
            return self.configured_path
        # Check PATH for stockfish / stockfish.exe
        for name in ("stockfish", "stockfish.exe"):
            found = shutil.which(name)
            if found:
                return found
        return None

    @property
    def is_available(self) -> bool:
        """Returns True if a valid Stockfish executable is detected."""
        return self._resolved_path is not None and os.path.isfile(self._resolved_path)

    @property
    def unavailable_reason(self) -> str | None:
        if not self.is_available:
            return "Stockfish not installed. Engine-dependent metrics (centipawn loss, blunder rate) are unavailable."
        return None

    def get_version(self) -> str | None:
        if not self.is_available:
            return None
        return f"Stockfish ({os.path.basename(self._resolved_path or '')})"

    def _get_engine_sync(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            if not self._resolved_path:
                raise RuntimeError("Stockfish binary not available")
            self._engine = chess.engine.SimpleEngine.popen_uci(self._resolved_path)
            try:
                self._engine.configure({"Skill Level": self.skill_level})
            except Exception as exc:
                logger.debug("Failed setting Skill Level on Stockfish: %s", exc)
        return self._engine

    def _analyse_position_sync(
        self, board: chess.Board, depth: int | None = None
    ) -> dict[str, Any]:
        """Analyse position synchronously using fixed depth or nodes."""
        engine = self._get_engine_sync()
        target_depth = depth or self.depth
        limit = (
            chess.engine.Limit(nodes=self.nodes)
            if self.nodes
            else chess.engine.Limit(depth=target_depth)
        )
        info = engine.analyse(board, limit)
        score_pov = info.get("score")
        cp_score: int | None = None
        is_mate: bool = False
        mate_moves: int | None = None

        if score_pov:
            # Score from White's perspective for absolute evaluation
            white_score = score_pov.white()
            if white_score.is_mate():
                is_mate = True
                mate_moves = white_score.mate()
                cp_score = MATE_SCORE_CAP if (mate_moves and mate_moves > 0) else -MATE_SCORE_CAP
            else:
                cp_score = white_score.score()

        best_move = None
        pv = info.get("pv")
        if pv and len(pv) > 0:
            best_move = pv[0].uci()

        return {
            "score_cp": cp_score,
            "is_mate": is_mate,
            "mate_moves": mate_moves,
            "best_move": best_move,
            "depth": info.get("depth", target_depth),
        }

    async def analyse_position(
        self, board: chess.Board, depth: int | None = None
    ) -> dict[str, Any]:
        """Thread-pool protected analysis of a board position."""
        if not self.is_available:
            return {
                "score_cp": None,
                "is_mate": False,
                "mate_moves": None,
                "best_move": None,
                "unavailable": True,
                "unavailable_reason": self.unavailable_reason,
            }
        async with self._lock:
            return await asyncio.to_thread(self._analyse_position_sync, board, depth)

    def _play_move_sync(
        self, board: chess.Board, depth: int | None = None
    ) -> chess.Move | None:
        """Play a move using the configured skill level and limits."""
        engine = self._get_engine_sync()
        target_depth = depth or self.depth
        limit = (
            chess.engine.Limit(nodes=self.nodes)
            if self.nodes
            else chess.engine.Limit(depth=target_depth)
        )
        result = engine.play(board, limit)
        return result.move

    async def play_move(
        self, board: chess.Board, depth: int | None = None
    ) -> chess.Move | None:
        """Thread-pool protected engine move selection."""
        if not self.is_available:
            return None
        async with self._lock:
            return await asyncio.to_thread(self._play_move_sync, board, depth)

    def evaluate_move_sync(
        self, board: chess.Board, move: chess.Move
    ) -> dict[str, Any]:
        """Evaluate a move by comparing evaluation before and after from player's POV."""
        analysis_before = self._analyse_position_sync(board)
        eval_before_white = analysis_before.get("score_cp") or 0.0

        board_after = board.copy()
        board_after.push(move)
        analysis_after = self._analyse_position_sync(board_after)
        eval_after_white = analysis_after.get("score_cp") or 0.0

        if board.turn == chess.WHITE:
            cp_loss = max(0.0, float(eval_before_white - eval_after_white))
        else:
            cp_loss = max(0.0, float(eval_after_white - eval_before_white))

        is_blunder = cp_loss >= settings.blunder_threshold_cp
        return {
            "eval_before": eval_before_white,
            "eval_after": eval_after_white,
            "centipawn_loss": cp_loss,
            "is_blunder": is_blunder,
            "best_move": analysis_before.get("best_move"),
        }

    async def evaluate_move(
        self, board: chess.Board, move: chess.Move
    ) -> dict[str, Any]:
        if not self.is_available:
            return {
                "eval_before": None,
                "eval_after": None,
                "centipawn_loss": None,
                "is_blunder": False,
                "best_move": None,
            }
        async with self._lock:
            return await asyncio.to_thread(self.evaluate_move_sync, board, move)

    def close(self) -> None:
        if self._engine:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None


class StubChessEngine(ChessEngineAdapter):
    """Deterministic in-memory stub engine for tests and offline environments.

    Calculates heuristic piece counts or returns predetermined moves without Stockfish.
    """

    def __init__(self, fixed_eval_cp: int = 50, blunder_on_moves: list[str] | None = None) -> None:
        super().__init__(binary_path="__stub__")
        self.fixed_eval_cp = fixed_eval_cp
        self.blunder_on_moves = blunder_on_moves or []
        self._resolved_path = "__stub__"

    @property
    def is_available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None

    def get_version(self) -> str | None:
        return "StubEngine (Test Double v1.0)"

    async def analyse_position(
        self, board: chess.Board, depth: int | None = None
    ) -> dict[str, Any]:
        # Count material as simple heuristic: P=100, N/B=300, R=500, Q=900
        piece_vals = {
            chess.PAWN: 100,
            chess.KNIGHT: 300,
            chess.BISHOP: 300,
            chess.ROOK: 500,
            chess.QUEEN: 900,
        }
        val = 0
        for sq in chess.SQUARES:
            p = board.piece_at(sq)
            if p:
                factor = 1 if p.color == chess.WHITE else -1
                val += factor * piece_vals.get(p.piece_type, 0)

        best = list(board.legal_moves)[0].uci() if list(board.legal_moves) else None
        return {
            "score_cp": val if val != 0 else self.fixed_eval_cp,
            "is_mate": board.is_checkmate(),
            "mate_moves": 1 if board.is_checkmate() else None,
            "best_move": best,
            "depth": depth or 10,
        }

    async def play_move(
        self, board: chess.Board, depth: int | None = None
    ) -> chess.Move | None:
        moves = list(board.legal_moves)
        if not moves:
            return None
        return moves[0]

    def evaluate_move_sync(
        self, board: chess.Board, move: chess.Move
    ) -> dict[str, Any]:
        uci = move.uci()
        san = board.san(move) if move in board.legal_moves else ""
        is_blunder = (uci in self.blunder_on_moves) or (san in self.blunder_on_moves)
        cp_loss = 450.0 if is_blunder else 15.0
        return {
            "eval_before": self.fixed_eval_cp,
            "eval_after": self.fixed_eval_cp - cp_loss if board.turn == chess.WHITE else self.fixed_eval_cp + cp_loss,
            "centipawn_loss": cp_loss,
            "is_blunder": is_blunder,
            "best_move": list(board.legal_moves)[0].uci() if list(board.legal_moves) else None,
        }

    async def evaluate_move(
        self, board: chess.Board, move: chess.Move
    ) -> dict[str, Any]:
        return self.evaluate_move_sync(board, move)


_GLOBAL_ENGINE: ChessEngineAdapter | None = None


def get_chess_engine() -> ChessEngineAdapter:
    """Return the global chess engine adapter instance."""
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = ChessEngineAdapter()
    return _GLOBAL_ENGINE


def set_chess_engine(engine: ChessEngineAdapter | None) -> None:
    """Set the global engine adapter (useful for testing with StubChessEngine)."""
    global _GLOBAL_ENGINE
    _GLOBAL_ENGINE = engine

