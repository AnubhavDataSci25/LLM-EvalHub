"""Game run and move persistence models for Reasoning Arena."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin

if TYPE_CHECKING:
    pass


class GameRun(IDMixin, TimestampMixin, Base):
    """An execution of an interactive reasoning game or game-based benchmark."""

    __tablename__ = "game_runs"

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        default="wks_default",
        nullable=False,
        index=True,
    )
    evaluation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    game_type: Mapped[str] = mapped_column(String(48), default="chess", index=True)
    task_type: Mapped[str] = mapped_column(String(48), default="game", index=True)
    model_id: Mapped[str] = mapped_column(String(128), index=True)
    provider_key: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    moves: Mapped[list[GameMove]] = relationship(
        "GameMove",
        back_populates="game_run",
        cascade="all, delete-orphan",
        order_by="GameMove.ply",
    )


class GameMove(IDMixin, TimestampMixin, Base):
    """A single ply / move record in a reasoning game run."""

    __tablename__ = "game_moves"

    game_run_id: Mapped[str] = mapped_column(
        ForeignKey("game_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ply: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    turn: Mapped[str] = mapped_column(String(16), default="white")
    fen_before: Mapped[str] = mapped_column(Text, nullable=False)
    fen_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_model_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_move: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_legal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_parseable: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    engine_eval_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_eval_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    centipawn_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_blunder: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    commentary: Mapped[str | None] = mapped_column(Text, nullable=True)

    game_run: Mapped[GameRun] = relationship("GameRun", back_populates="moves")
