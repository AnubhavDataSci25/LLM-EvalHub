"""Pydantic schemas for Reasoning Arena: Chess."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ArenaChessRunCreate(BaseModel):
    """Configuration to start a game or dry-run in Reasoning Arena."""

    model_id: str = Field(..., description="Target model ID to benchmark")
    provider_key: str = Field("mock", description="Provider key (mock, openai, anthropic, google, etc.)")
    task_type: str = Field("game", description="Task type: 'game', 'puzzle_suite', or 'legal_moves'")
    model_color: str = Field("white", description="Player color: 'white' or 'black'")
    prompt_variant: str = Field("fen_ascii", description="Prompt variant: 'fen_only', 'fen_ascii', 'fen_legal_moves', 'fen_ascii_legal'")
    think_step_by_step: bool = Field(False, description="Whether to include step-by-step reasoning instructions")
    temperature: float = Field(0.0, ge=0.0, le=2.0, description="Model generation temperature")
    max_moves: int = Field(60, ge=1, le=200, description="Hard maximum moves per game to bound quota")
    max_retries: int = Field(1, ge=0, le=3, description="Retry attempts for illegal moves before forfeit")
    opponent_skill_level: int = Field(5, ge=0, le=20, description="Stockfish skill level (0-20)")
    dry_run: bool = Field(False, description="If True, returns call estimation without executing")


class ArenaDryRunEstimate(BaseModel):
    """Dry-run quota estimation for an arena run."""

    task_type: str
    model_id: str
    provider_key: str
    estimated_calls: int
    max_moves: int
    max_retries_per_move: int
    estimated_tokens_upper_bound: int
    message: str


class GameMoveOut(BaseModel):
    """Single ply / move record in an arena game."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    game_run_id: str
    ply: int
    turn: str
    fen_before: str
    fen_after: str | None = None
    raw_model_output: str | None = None
    parsed_move: str | None = None
    is_legal: bool
    is_parseable: bool
    retry_count: int = 0
    engine_eval_before: float | None = None
    engine_eval_after: float | None = None
    centipawn_loss: float | None = None
    is_blunder: bool = False
    latency_ms: float | None = None
    commentary: str | None = None
    created_at: datetime


class GameRunOut(BaseModel):
    """Full game run response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    evaluation_run_id: str | None = None
    game_type: str = "chess"
    task_type: str
    model_id: str
    provider_key: str
    status: str
    config: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    moves: list[GameMoveOut] = Field(default_factory=list)


class ArenaChessStatus(BaseModel):
    """Stockfish status and engine availability information."""

    stockfish_available: bool
    stockfish_path: str | None = None
    stockfish_version: str | None = None
    unavailable_reason: str | None = None
    supported_prompt_variants: list[str] = [
        "fen_only",
        "fen_ascii",
        "fen_legal_moves",
        "fen_ascii_legal",
    ]
    supported_task_types: list[str] = ["game", "puzzle_suite", "legal_moves"]
    default_config: dict[str, Any] = {
        "depth": 10,
        "skill_level": 5,
        "max_moves": 60,
        "max_retries": 1,
        "blunder_threshold_cp": 300,
    }


class ArenaChessSummary(BaseModel):
    """Aggregated stats across arena runs."""

    total_runs: int = 0
    completed_games: int = 0
    model_wins: int = 0
    engine_wins: int = 0
    draws: int = 0
    forfeits: int = 0
    overall_legal_move_rate: float | None = None
    overall_puzzle_accuracy: float | None = None
    models_evaluated: list[str] = Field(default_factory=list)
