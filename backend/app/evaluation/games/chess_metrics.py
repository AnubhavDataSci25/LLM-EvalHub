"""Deterministic chess evaluation metrics.

Evaluates chess-based reasoning tasks (legal move compliance, format compliance,
puzzle accuracy, mate finding, centipawn loss, and blunder rate) without requiring
an LLM judge.
"""

from __future__ import annotations

import re
from typing import Any

import chess

from app.core.config import settings
from app.evaluation.games.chess_env import ChessEnvironment
from app.evaluation.games.engine import get_chess_engine
from app.evaluation.metrics import MetricOutcome

_FEN_REGEX = re.compile(
    r"\b((?:[rnbqkpRNBQKP1-8]+/){7}[rnbqkpRNBQKP1-8]+)\s+([wb])\s+([KQkq\-]+)\s+([a-h1-8\-]+)\s+(\d+)\s+(\d+)\b"
)


def extract_fen(question: str, extra_metadata: dict[str, Any] | None = None) -> str | None:
    """Extract valid FEN from extra metadata or question text."""
    if extra_metadata and extra_metadata.get("fen"):
        candidate = str(extra_metadata["fen"]).strip()
        try:
            chess.Board(candidate)
            return candidate
        except Exception:
            pass

    if not question:
        return None

    # Check for Position (FEN): <fen>
    fen_match = re.search(r"Position\s*\([Ff][Ee][Nn]\)\s*:\s*([^\r\n]+)", question)
    if fen_match:
        cand = fen_match.group(1).strip()
        try:
            chess.Board(cand)
            return cand
        except Exception:
            pass

    match = _FEN_REGEX.search(question)
    if match:
        cand = match.group(0).strip()
        try:
            chess.Board(cand)
            return cand
        except Exception:
            pass

    return None


def _clean_move_token(token: str) -> str:
    cleaned = token.strip().strip(".!:,;\"'`*")
    if cleaned in ("0-0", "o-o"):
        return "O-O"
    if cleaned in ("0-0-0", "o-o-o"):
        return "O-O-O"
    return cleaned


def evaluate_chess_metrics(
    *,
    question: str,
    answer: str | None,
    ground_truth: str | None,
    extra_metadata: dict[str, Any] | None = None,
    engine: Any | None = None,
) -> dict[str, MetricOutcome]:
    """Score all 6 chess reasoning metrics synchronously / deterministically.

    Engine evaluation is used for centipawn loss and blunder rate if engine is provided.
    If engine is absent, those metrics return unavailable with the explicit reason:
    'Stockfish not installed'.
    """
    meta = extra_metadata or {}
    fen = extract_fen(question, meta)

    if not fen:
        reason = "No valid chess FEN found in inputs or metadata"
        return {
            "legal_move_rate": MetricOutcome.unavailable("legal_move_rate", reason),
            "format_compliance_rate": MetricOutcome.unavailable("format_compliance_rate", reason),
            "puzzle_accuracy": MetricOutcome.unavailable("puzzle_accuracy", reason),
            "mate_found_rate": MetricOutcome.unavailable("mate_found_rate", reason),
            "avg_centipawn_loss": MetricOutcome.unavailable("avg_centipawn_loss", "Stockfish not installed"),
            "blunder_rate": MetricOutcome.unavailable("blunder_rate", "Stockfish not installed"),
        }

    try:
        board = chess.Board(fen)
    except Exception as exc:
        reason = f"Invalid FEN position: {exc}"
        return {
            "legal_move_rate": MetricOutcome.unavailable("legal_move_rate", reason),
            "format_compliance_rate": MetricOutcome.unavailable("format_compliance_rate", reason),
            "puzzle_accuracy": MetricOutcome.unavailable("puzzle_accuracy", reason),
            "mate_found_rate": MetricOutcome.unavailable("mate_found_rate", reason),
            "avg_centipawn_loss": MetricOutcome.unavailable("avg_centipawn_loss", "Stockfish not installed"),
            "blunder_rate": MetricOutcome.unavailable("blunder_rate", "Stockfish not installed"),
        }

    env = ChessEnvironment(engine_adapter=engine)
    env.load_position(fen)
    action = env.parse_action(answer or "")

    outcomes: dict[str, MetricOutcome] = {}

    # 1. Format compliance
    is_fmt = 1.0 if action.is_parseable else 0.0
    outcomes["format_compliance_rate"] = MetricOutcome(
        metric="format_compliance_rate",
        raw_score=is_fmt,
        normalized_score=is_fmt,
        confidence=0.98,
        evidence=f"Parsed move token '{action.parsed}'" if action.is_parseable else "No recognizable move format",
        available=True,
        details={"parsed": action.parsed, "error_reason": action.error_reason},
    )

    # 2. Legal move rate
    is_legal = 1.0 if action.is_legal else 0.0
    outcomes["legal_move_rate"] = MetricOutcome(
        metric="legal_move_rate",
        raw_score=is_legal,
        normalized_score=is_legal,
        confidence=1.0,
        evidence=f"Move '{action.parsed}' is legal" if action.is_legal else f"Illegal move: {action.error_reason}",
        available=True,
        details={
            "parsed": action.parsed,
            "is_legal": action.is_legal,
            "error_reason": action.error_reason,
        },
    )

    # 3. Puzzle accuracy
    if not ground_truth or not ground_truth.strip():
        outcomes["puzzle_accuracy"] = MetricOutcome.unavailable(
            "puzzle_accuracy", "No ground truth solution provided"
        )
    else:
        # Check against ground truth tokens
        gt_tokens = re.split(r"[;\s,]+", ground_truth.strip())
        expected_moves = [_clean_move_token(t) for t in gt_tokens if t.strip()]
        first_expected = expected_moves[0] if expected_moves else None

        is_correct = False
        if action.is_legal and first_expected and action.parsed:
            # Check SAN match
            if action.parsed.lower() == first_expected.lower():
                is_correct = True
            elif action.metadata and action.metadata.get("uci"):
                if action.metadata["uci"].lower() == first_expected.lower():
                    is_correct = True
            # Also check if python-chess interprets first_expected as the same move
            if not is_correct:
                try:
                    exp_move = board.parse_san(first_expected)
                    if board.san(exp_move) == action.parsed:
                        is_correct = True
                except Exception:
                    try:
                        exp_move = board.parse_uci(first_expected.lower())
                        if board.san(exp_move) == action.parsed:
                            is_correct = True
                    except Exception:
                        pass

        acc_score = 1.0 if is_correct else 0.0
        outcomes["puzzle_accuracy"] = MetricOutcome(
            metric="puzzle_accuracy",
            raw_score=acc_score,
            normalized_score=acc_score,
            confidence=1.0,
            evidence=f"Produced '{action.parsed}', expected '{first_expected}'",
            available=True,
            details={"expected": first_expected, "actual": action.parsed, "matches": is_correct},
        )

    # 4. Mate found rate
    theme = str(meta.get("theme", "")).lower()
    is_mate_problem = (
        "mate" in theme
        or (ground_truth and "#" in ground_truth)
        or bool(meta.get("is_mate"))
    )

    if not is_mate_problem:
        outcomes["mate_found_rate"] = MetricOutcome.unavailable(
            "mate_found_rate", "Position does not contain a forced checkmate"
        )
    else:
        mate_found = False
        if action.is_legal and action.metadata and action.metadata.get("uci"):
            move_obj = chess.Move.from_uci(action.metadata["uci"])
            if board.is_into_check(move_obj):
                pass
            test_board = board.copy()
            test_board.push(move_obj)
            if test_board.is_checkmate():
                mate_found = True
            elif outcomes.get("puzzle_accuracy") and outcomes["puzzle_accuracy"].raw_score == 1.0:
                mate_found = True

        m_score = 1.0 if mate_found else 0.0
        outcomes["mate_found_rate"] = MetricOutcome(
            metric="mate_found_rate",
            raw_score=m_score,
            normalized_score=m_score,
            confidence=1.0,
            evidence=f"Delivered mate or solution: {mate_found}",
            available=True,
            details={"mate_found": mate_found},
        )

    # 5 & 6. Stockfish-dependent metrics: avg_centipawn_loss and blunder_rate
    effective_engine = engine or get_chess_engine()
    if effective_engine is None or not effective_engine.is_available:
        outcomes["avg_centipawn_loss"] = MetricOutcome.unavailable(
            "avg_centipawn_loss", "Stockfish not installed"
        )
        outcomes["blunder_rate"] = MetricOutcome.unavailable(
            "blunder_rate", "Stockfish not installed"
        )
    else:
        # Engine is available, evaluate loss if move is legal
        if not action.is_legal or not action.metadata or not action.metadata.get("uci"):
            # Move not legal, loss cannot be measured
            outcomes["avg_centipawn_loss"] = MetricOutcome.unavailable(
                "avg_centipawn_loss", "Move was illegal or unparseable"
            )
            outcomes["blunder_rate"] = MetricOutcome.unavailable(
                "blunder_rate", "Move was illegal or unparseable"
            )
        else:
            try:
                move_uci = action.metadata["uci"]
                analysis = effective_engine.evaluate_move_sync(board, chess.Move.from_uci(move_uci))
                cp_loss = analysis.get("centipawn_loss", 0.0)
                is_blunder = analysis.get("is_blunder", False)

                # Centipawn loss (lower is better: raw is cp_loss, normalized 0..1 where 1 is 0 loss)
                norm_loss = max(0.0, min(1.0, 1.0 - (cp_loss / 1000.0)))
                outcomes["avg_centipawn_loss"] = MetricOutcome(
                    metric="avg_centipawn_loss",
                    raw_score=round(cp_loss, 2),
                    normalized_score=round(norm_loss, 4),
                    confidence=0.95,
                    evidence=f"Centipawn loss: {cp_loss:.1f} cp against engine",
                    available=True,
                    details={"centipawn_loss": cp_loss, "eval_before": analysis.get("eval_before"), "eval_after": analysis.get("eval_after")},
                )

                # Blunder rate (lower is better for raw, normalized 1.0 = no blunder, 0.0 = blunder)
                b_raw = 1.0 if is_blunder else 0.0
                outcomes["blunder_rate"] = MetricOutcome(
                    metric="blunder_rate",
                    raw_score=b_raw,
                    normalized_score=1.0 - b_raw,
                    confidence=0.95,
                    evidence="Move flagged as blunder (>300 cp loss)" if is_blunder else "Move is sound",
                    available=True,
                    details={"is_blunder": is_blunder, "threshold_cp": settings.blunder_threshold_cp},
                )
            except Exception as exc:
                outcomes["avg_centipawn_loss"] = MetricOutcome.unavailable(
                    "avg_centipawn_loss", f"Engine evaluation failed: {exc}"
                )
                outcomes["blunder_rate"] = MetricOutcome.unavailable(
                    "blunder_rate", f"Engine evaluation failed: {exc}"
                )

    return outcomes
