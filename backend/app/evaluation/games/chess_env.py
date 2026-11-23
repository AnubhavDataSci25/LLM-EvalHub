"""Chess environment implementation using python-chess.

Manages chess rules, FEN/PGN representation, prompt variants, strict move parsing
(SAN and UCI without guessing), and failure classification.
"""

from __future__ import annotations

import re
from typing import Any

import chess

from app.evaluation.games.base import (
    GameAction,
    GameEnvironment,
    GameObservation,
    GameStepResult,
)


class ChessEnvironment(GameEnvironment):
    """Full-rules chess environment wrapping python-chess."""

    def __init__(self, engine_adapter: Any | None = None) -> None:
        self.board = chess.Board()
        self.engine = engine_adapter
        self.move_history: list[dict[str, Any]] = []

    def reset(self, position: str | None = None) -> GameObservation:
        """Reset board to start or custom FEN position."""
        if position:
            self.board = chess.Board(position)
        else:
            self.board.reset()
        self.move_history.clear()
        return self._make_observation()

    def load_position(self, position_str: str) -> GameObservation:
        """Load board from a FEN string."""
        return self.reset(position_str)

    def _make_observation(self) -> GameObservation:
        return GameObservation(
            position_str=self.board.fen(),
            turn="white" if self.board.turn == chess.WHITE else "black",
            move_number=self.board.fullmove_number,
            legal_actions=[self.board.san(m) for m in self.board.legal_moves],
            is_terminal=self.board.is_game_over(),
            info={
                "is_check": self.board.is_check(),
                "halfmove_clock": self.board.halfmove_clock,
                "san_legal_moves": [self.board.san(m) for m in self.board.legal_moves],
                "uci_legal_moves": [m.uci() for m in self.board.legal_moves],
            },
        )

    def legal_actions(self, use_uci: bool = False) -> list[str]:
        if use_uci:
            return [m.uci() for m in self.board.legal_moves]
        return [self.board.san(m) for m in self.board.legal_moves]

    def ascii_board(self) -> str:
        """Render clean 8x8 ASCII board representation with rank and file labels."""
        lines = str(self.board).split("\n")
        numbered = []
        for rank_idx, line in enumerate(lines):
            rank_num = 8 - rank_idx
            numbered.append(f"{rank_num}  {line}")
        numbered.append("   a b c d e f g h")
        return "\n".join(numbered)

    def render_prompt(
        self,
        variant: str = "fen_only",
        think_step_by_step: bool = False,
        task_instruction: str = "What is the best move in this position?",
    ) -> str:
        """Render prompt text based on configured prompt variant."""
        turn_str = "White" if self.board.turn == chess.WHITE else "Black"
        sections = [
            f"You are playing chess. It is {turn_str}'s turn to move.",
            f"Position (FEN): {self.board.fen()}",
        ]

        if "ascii" in variant:
            sections.append(f"Board representation:\n```\n{self.ascii_board()}\n```")

        if "legal" in variant:
            legal_list = ", ".join(self.legal_actions())
            sections.append(f"Legal moves available: {legal_list}")

        sections.append(task_instruction)

        if think_step_by_step:
            sections.append(
                "Think step by step analyzing threats, tactics, and candidate moves. "
                "At the very end of your response, state your selected move on its own line exactly in the format: "
                "'Final Move: <move>' (using Standard Algebraic Notation, e.g. 'Nf3' or 'e4', or UCI format, e.g. 'e2e4')."
            )
        else:
            sections.append(
                "Respond with your chosen move. "
                "State your move in standard algebraic notation (SAN, e.g. 'e4', 'Nf3', 'O-O') "
                "or UCI notation (e.g. 'e2e4'). Conclude with: 'Final Move: <move>'."
            )

        return "\n\n".join(sections)

    def parse_action(self, raw_output: str) -> GameAction:
        """Strictly parse model output into a candidate chess move without guessing."""
        if not raw_output or not raw_output.strip():
            return GameAction(
                raw_text=raw_output or "",
                parsed=None,
                is_parseable=False,
                is_legal=False,
                error_reason="unparseable_move",
                metadata={"details": "Empty model output"},
            )

        cleaned = raw_output.strip()

        # 1. Look for explicit 'Final Move: <move>' or 'Move: <move>' declaration
        explicit_patterns = [
            r"(?:final\s+move|best\s+move|chosen\s+move|my\s+move\s+is|move)\s*[:=*\s]+\s*([a-hA-H1-8NBRQKx#+=O0\-]{2,7})",
            r"\*\*([a-hA-H1-8NBRQKx#+=O0\-]{2,7})\*\*",
        ]
        candidate_token = None
        for pattern in explicit_patterns:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                candidate_token = match.group(1).strip()
                break

        # 2. If no explicit prefix, inspect trailing text or individual tokens
        if not candidate_token:
            # Check if the whole string is just a single move token
            single_token = cleaned.strip().strip(".!:,;\"'`*")
            if re.match(r"^(?:[O0]-[O0](?:-[O0])?|[a-h][1-8][a-h][1-8][qrbnQRBN]?|[NBRQK]?[a-h]?[1-8]?x?[a-h][1-8](?:=[NBRQK])?[+#]?)$", single_token):
                candidate_token = single_token
            else:
                # Find all potential chess move tokens in the text
                tokens = re.findall(
                    r"\b(?:[O0]-[O0](?:-[O0])?|[a-h][1-8][a-h][1-8][qrbnQRBN]?|[NBRQK]?[a-h]?[1-8]?x?[a-h][1-8](?:=[NBRQK])?[+#]?)\b",
                    cleaned,
                )
                if tokens:
                    # Prefer the last mentioned candidate move token (conclusion of reasoning)
                    candidate_token = tokens[-1]

        if not candidate_token:
            return GameAction(
                raw_text=raw_output,
                parsed=None,
                is_parseable=False,
                is_legal=False,
                error_reason="unparseable_move",
                metadata={"details": "No recognizable chess move syntax found"},
            )

        # Normalise token
        token = candidate_token.strip().strip(".!:,;\"'`*")
        # Standardise castling notation
        if token in ("0-0", "o-o"):
            token = "O-O"
        elif token in ("0-0-0", "o-o-o"):
            token = "O-O-O"

        # Validate against python-chess board
        parsed_move: chess.Move | None = None
        is_legal = False
        error_reason: str | None = None

        # Check SAN
        try:
            parsed_move = self.board.parse_san(token)
            is_legal = parsed_move in self.board.legal_moves
        except Exception:
            # Check UCI
            try:
                parsed_move = self.board.parse_uci(token.lower())
                is_legal = parsed_move in self.board.legal_moves
            except Exception:
                pass

        if is_legal and parsed_move:
            san_str = self.board.san(parsed_move)
            return GameAction(
                raw_text=raw_output,
                parsed=san_str,
                is_parseable=True,
                is_legal=True,
                error_reason=None,
                metadata={
                    "uci": parsed_move.uci(),
                    "san": san_str,
                    "from_square": chess.square_name(parsed_move.from_square),
                    "to_square": chess.square_name(parsed_move.to_square),
                },
            )

        # Move syntax was extracted, but move is not legal in this position
        # Check if it was a turn confusion / opponent's legal move
        opp_board = self.board.copy(stack=False)
        opp_board.turn = not self.board.turn
        is_opp_legal = False
        try:
            opp_m = opp_board.parse_san(token)
            is_opp_legal = opp_m in opp_board.legal_moves
        except Exception:
            try:
                opp_m = opp_board.parse_uci(token.lower())
                is_opp_legal = opp_m in opp_board.legal_moves
            except Exception:
                pass

        if is_opp_legal or "..." in raw_output:
            error_reason = "wrong_color_or_turn_confusion"
        else:
            error_reason = "illegal_move"

        return GameAction(
            raw_text=raw_output,
            parsed=token,
            is_parseable=True,
            is_legal=False,
            error_reason=error_reason,
            metadata={"candidate_token": token, "is_opponent_legal": is_opp_legal},
        )

    def validate_action(self, action: GameAction) -> bool:
        return action.is_legal and action.parsed is not None

    def apply_action(self, action: GameAction) -> GameStepResult:
        """Apply legal action to the board and advance state."""
        if not action.is_legal or not action.parsed:
            return GameStepResult(
                observation=self._make_observation(),
                action=action,
                is_legal=False,
                is_terminal=True,
                reward=0.0,
                info={"error": action.error_reason or "illegal_move"},
            )

        # Execute move
        move = self.board.parse_san(action.parsed)
        uci = move.uci()
        san = self.board.san(move)
        fen_before = self.board.fen()
        self.board.push(move)
        fen_after = self.board.fen()

        is_term = self.board.is_game_over()
        reward = 0.0
        if is_term:
            res = self.board.result()
            if res == "1-0":
                reward = 1.0  # White won
            elif res == "0-1":
                reward = -1.0  # Black won
            else:
                reward = 0.5  # Draw

        self.move_history.append(
            {
                "fen_before": fen_before,
                "fen_after": fen_after,
                "san": san,
                "uci": uci,
                "ply": len(self.board.move_stack),
            }
        )

        return GameStepResult(
            observation=self._make_observation(),
            action=action,
            is_legal=True,
            is_terminal=is_term,
            reward=reward,
            info={"fen_after": fen_after, "result": self.board.result() if is_term else None},
        )

    def evaluate_action(
        self,
        action: GameAction,
        solution_line: list[str] | None = None,
        is_puzzle: bool = False,
    ) -> dict[str, Any]:
        """Evaluate an action against ground truth and/or engine."""
        eval_result: dict[str, Any] = {
            "is_legal": action.is_legal,
            "is_parseable": action.is_parseable,
            "puzzle_solved": False,
            "is_blunder": False,
            "centipawn_loss": None,
            "engine_available": self.engine.is_available if self.engine else False,
        }

        if is_puzzle and solution_line and action.is_legal and action.parsed:
            # Check if action matches puzzle solution (first move in solution line)
            first_expected = solution_line[0] if solution_line else None
            # Normalise comparison (SAN or UCI)
            action_uci = action.metadata.get("uci")
            if (
                action.parsed.lower() == (first_expected or "").lower()
                or (action_uci and action_uci.lower() == (first_expected or "").lower())
            ):
                eval_result["puzzle_solved"] = True

        return eval_result

    def is_terminal(self) -> bool:
        return self.board.is_game_over()

    def outcome(self) -> dict[str, Any] | None:
        if not self.is_terminal():
            return None
        res = self.board.result()
        reason = "unknown"
        if self.board.is_checkmate():
            reason = "checkmate"
        elif self.board.is_stalemate():
            reason = "stalemate"
        elif self.board.is_insufficient_material():
            reason = "insufficient_material"
        elif self.board.is_seventyfive_moves():
            reason = "seventyfive_moves"
        elif self.board.is_fivefold_repetition():
            reason = "fivefold_repetition"

        return {
            "result": res,
            "reason": reason,
            "winner": "white" if res == "1-0" else "black" if res == "0-1" else "draw",
        }
