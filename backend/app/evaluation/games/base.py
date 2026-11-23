"""Generic game environment abstraction for reasoning benchmarks.

Provides a unified interface across games (Chess, and future board/card games)
for state representation, action parsing, rules validation, and evaluation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GameAction:
    """Parsed model action in a game environment."""

    raw_text: str
    parsed: str | None = None
    is_parseable: bool = False
    is_legal: bool = False
    error_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameObservation:
    """Current state observation returned to the model."""

    position_str: str
    turn: str
    move_number: int
    legal_actions: list[str] = field(default_factory=list)
    is_terminal: bool = False
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameStepResult:
    """Result of applying an action in the environment."""

    observation: GameObservation
    action: GameAction
    is_legal: bool
    is_terminal: bool
    reward: float = 0.0
    info: dict[str, Any] = field(default_factory=dict)


class GameEnvironment(ABC):
    """Abstract interface for game-based reasoning benchmarks.

    Enforces separation between model generation, game rules, action validation,
    and engine-assisted evaluation.
    """

    @abstractmethod
    def reset(self, position: str | None = None) -> GameObservation:
        """Reset environment to standard initial state or given position."""

    @abstractmethod
    def load_position(self, position_str: str) -> GameObservation:
        """Load an arbitrary position/board state."""

    @abstractmethod
    def render_prompt(self, variant: str = "fen_only", think_step_by_step: bool = False) -> str:
        """Render instructions and current state for the LLM prompt."""

    @abstractmethod
    def parse_action(self, raw_output: str) -> GameAction:
        """Parse raw LLM output into a game action without guessing."""

    @abstractmethod
    def validate_action(self, action: GameAction) -> bool:
        """Check whether the action is legal in the current position."""

    @abstractmethod
    def apply_action(self, action: GameAction) -> GameStepResult:
        """Apply a validated action and transition to the next state."""

    @abstractmethod
    def evaluate_action(self, action: GameAction) -> dict[str, Any]:
        """Compute evaluation metrics for the action (e.g. centipawn loss, blunder)."""

    @abstractmethod
    def is_terminal(self) -> bool:
        """Return True if the game is over (checkmate, draw, resign, cap)."""

    @abstractmethod
    def outcome(self) -> dict[str, Any] | None:
        """Return outcome details if terminal (winner, termination reason)."""

    @abstractmethod
    def legal_actions(self) -> list[str]:
        """List all legal action notations available in the current state."""
