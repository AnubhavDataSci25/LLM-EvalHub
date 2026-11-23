"""Tests for Reasoning Arena: Chess benchmark, environment, metrics, workflow, and API routes."""

from __future__ import annotations

import pytest

from app.evaluation.failure_detector import classify
from app.evaluation.games.chess_env import ChessEnvironment
from app.evaluation.games.chess_metrics import evaluate_chess_metrics, extract_fen
from app.evaluation.games.engine import StubChessEngine
from app.evaluation.registry import METRIC_SPECS, EvaluationInputs, Evaluator
from app.providers.mock import MockProvider
from app.services.arena_service import ArenaService
from app.services.benchmark_service import BenchmarkService
from app.services.recommendation_service import PROFILES, RANKABLE_METRICS


def test_fen_extraction():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    # Extraction from prompt text
    prompt = f"You are playing chess. Position (FEN): {fen}\nWhat is the best move?"
    extracted = extract_fen(prompt)
    assert extracted == fen

    # Extraction from metadata
    assert extract_fen("", {"fen": fen}) == fen

    # Invalid input
    assert extract_fen("no fen here") is None


def test_chess_move_parsing():
    env = ChessEnvironment()
    env.reset()

    # Explicit format: Final Move: <move>
    action1 = env.parse_action("Thinking step by step...\nFinal Move: e4")
    assert action1.is_parseable is True
    assert action1.is_legal is True
    assert action1.parsed == "e4"

    # UCI format
    action2 = env.parse_action("I choose move: e2e4")
    assert action2.is_parseable is True
    assert action2.is_legal is True
    assert action2.parsed == "e4"

    # Single token output
    action3 = env.parse_action("Nf3")
    assert action3.is_parseable is True
    assert action3.is_legal is True
    assert action3.parsed == "Nf3"

    # Castling notation
    env.load_position("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 6 5")
    action_castle = env.parse_action("Final Move: O-O")
    assert action_castle.is_legal is True
    assert action_castle.parsed == "O-O"

    # Unparseable output (commentary only)
    action_unparseable = env.parse_action("White has great pawn control. I recommend playing defensively.")
    assert action_unparseable.is_parseable is False
    assert action_unparseable.is_legal is False
    assert action_unparseable.error_reason == "unparseable_move"

    # Illegal move syntax / coordinate
    action_illegal = env.parse_action("Final Move: Ke9")
    assert action_illegal.is_legal is False
    assert action_illegal.error_reason == "illegal_move"

    # Turn confusion (opponent's legal move: e7-e5 is Black's move, but White is to move)
    env.reset()
    action_opp = env.parse_action("Final Move: e5")
    assert action_opp.is_legal is False
    assert action_opp.error_reason == "wrong_color_or_turn_confusion"


def test_chess_metrics_evaluation_without_stockfish():
    fen = "r1bqkb1r/pppp1ppp/2n5/4p3/2B1n3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 5"
    prompt = f"Position (FEN): {fen}\nChoose your move."

    # Legal move evaluation
    outcomes = evaluate_chess_metrics(
        question=prompt,
        answer="Final Move: Nxe5",
        ground_truth="Nxe5",
        extra_metadata={"theme": "tactics"},
        engine=None,
    )

    assert outcomes["legal_move_rate"].raw_score == 1.0
    assert outcomes["format_compliance_rate"].raw_score == 1.0
    assert outcomes["puzzle_accuracy"].raw_score == 1.0
    # Engine metrics must report unavailable with the required reason
    assert outcomes["avg_centipawn_loss"].available is False
    assert outcomes["avg_centipawn_loss"].unavailable_reason == "Stockfish not installed"
    assert outcomes["blunder_rate"].available is False
    assert outcomes["blunder_rate"].unavailable_reason == "Stockfish not installed"


def test_chess_metrics_with_stub_engine():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    stub = StubChessEngine(fixed_eval_cp=20, blunder_on_moves=["h4"])

    # Sound move
    outcomes_sound = evaluate_chess_metrics(
        question=f"Position (FEN): {fen}",
        answer="Final Move: e4",
        ground_truth="e4",
        engine=stub,
    )
    assert outcomes_sound["avg_centipawn_loss"].available is True
    assert outcomes_sound["avg_centipawn_loss"].raw_score == 15.0
    assert outcomes_sound["blunder_rate"].raw_score == 0.0

    # Blunder move
    outcomes_blunder = evaluate_chess_metrics(
        question=f"Position (FEN): {fen}",
        answer="Final Move: h4",
        ground_truth="e4",
        engine=stub,
    )
    assert outcomes_blunder["blunder_rate"].raw_score == 1.0
    assert outcomes_blunder["avg_centipawn_loss"].raw_score == 450.0


def test_chess_mate_detection():
    # Scholar's mate position (White to deliver Qxf7#)
    fen = "r1bqkb1r/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 2 4"
    prompt = f"Position (FEN): {fen}"

    # Model delivers mate
    mate_outcomes = evaluate_chess_metrics(
        question=prompt,
        answer="Final Move: Qxf7#",
        ground_truth="Qxf7#",
        extra_metadata={"theme": "mateIn1", "is_mate": True},
    )
    assert mate_outcomes["mate_found_rate"].raw_score == 1.0
    assert mate_outcomes["puzzle_accuracy"].raw_score == 1.0

    # Model misses mate
    miss_outcomes = evaluate_chess_metrics(
        question=prompt,
        answer="Final Move: Nf3",
        ground_truth="Qxf7#",
        extra_metadata={"theme": "mateIn1", "is_mate": True},
    )
    assert miss_outcomes["mate_found_rate"].raw_score == 0.0
    assert miss_outcomes["puzzle_accuracy"].raw_score == 0.0


def test_evaluator_integration_with_chess_metrics():
    evaluator = Evaluator(
        metrics=[
            "legal_move_rate",
            "format_compliance_rate",
            "puzzle_accuracy",
            "mate_found_rate",
            "avg_centipawn_loss",
            "blunder_rate",
        ]
    )

    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    inputs = EvaluationInputs(
        question=f"Position (FEN): {fen}",
        answer="Final Move: e4",
        ground_truth="e4",
        contexts=[],
        latency_ms=120.0,
        extra_metadata={"fen": fen},
    )

    import asyncio

    outcomes = asyncio.run(evaluator.evaluate(inputs))
    scored = {o.metric: o for o in outcomes}

    assert scored["legal_move_rate"].raw_score == 1.0
    assert scored["format_compliance_rate"].raw_score == 1.0
    assert scored["puzzle_accuracy"].raw_score == 1.0
    assert scored["avg_centipawn_loss"].available is False  # Stockfish absent


def test_failure_classification_for_chess():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    # 1. Unparseable move
    outcomes_unparseable = evaluate_chess_metrics(
        question=f"Position (FEN): {fen}",
        answer="I don't know chess.",
        ground_truth="e4",
    )
    verdict1 = classify(
        answer="I don't know chess.",
        ground_truth="e4",
        contexts=[],
        outcomes=list(outcomes_unparseable.values()),
        latency_ms=100.0,
    )
    assert verdict1.failed is True
    assert verdict1.failure_type == "unparseable_move"

    # 2. Illegal move
    outcomes_illegal = evaluate_chess_metrics(
        question=f"Position (FEN): {fen}",
        answer="Final Move: Ke9",
        ground_truth="e4",
    )
    verdict2 = classify(
        answer="Final Move: Ke9",
        ground_truth="e4",
        contexts=[],
        outcomes=list(outcomes_illegal.values()),
        latency_ms=100.0,
    )
    assert verdict2.failed is True
    assert verdict2.failure_type == "illegal_move"

    # 3. Turn confusion
    outcomes_turn = evaluate_chess_metrics(
        question=f"Position (FEN): {fen}",
        answer="Final Move: e5",
        ground_truth="e4",
    )
    verdict3 = classify(
        answer="Final Move: e5",
        ground_truth="e4",
        contexts=[],
        outcomes=list(outcomes_turn.values()),
        latency_ms=100.0,
    )
    assert verdict3.failed is True
    assert verdict3.failure_type == "wrong_color_or_turn_confusion"


def test_recommendation_game_reasoning_profile():
    assert "game_reasoning" in PROFILES
    weights = PROFILES["game_reasoning"]
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["legal_move_rate"] == 0.35
    assert weights["puzzle_accuracy"] == 0.30

    # Ensure all chess metrics in profile are rankable
    for m in ("legal_move_rate", "puzzle_accuracy", "blunder_rate", "format_compliance_rate"):
        assert m in RANKABLE_METRICS
        assert METRIC_SPECS[m].group == "game_reasoning"


def test_benchmark_pack_chess_reasoning(db):
    service = BenchmarkService(db)
    packs = service.list_packs()
    pack_map = {p.key: p for p in packs}
    assert "chess_reasoning" in pack_map

    pack_detail = service.get_pack("chess_reasoning")
    assert pack_detail.name == "Reasoning Arena: Chess"
    assert "legal_move_rate" in pack_detail.metrics
    assert "puzzle_accuracy" in pack_detail.metrics
    assert pack_detail.case_count == 76


def test_mock_provider_chess_modes():
    provider = MockProvider()
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    prompt = f"Position (FEN): {fen}\nPlay your move."

    import asyncio

    # mock-chess-legal
    resp_legal = asyncio.run(provider.generate(prompt=prompt, model="mock-chess-legal"))
    assert "Final Move:" in resp_legal.text
    # Verify move is strictly legal
    env = ChessEnvironment()
    env.load_position(fen)
    action = env.parse_action(resp_legal.text)
    assert action.is_legal is True

    # mock-chess-illegal
    resp_illegal = asyncio.run(provider.generate(prompt=prompt, model="mock-chess-illegal"))
    assert "Final Move: Ke9" in resp_illegal.text

    # mock-chess-unparseable
    resp_unparseable = asyncio.run(provider.generate(prompt=prompt, model="mock-chess-unparseable"))
    action_unp = env.parse_action(resp_unparseable.text)
    assert action_unp.is_parseable is False

    # mock-chess-verbose
    resp_verbose = asyncio.run(provider.generate(prompt=prompt, model="mock-chess-verbose"))
    assert "Thinking step by step" in resp_verbose.text
    assert "Final Move:" in resp_verbose.text


def test_arena_dry_run_estimation(db):
    from app.schemas.arena import ArenaChessRunCreate

    service = ArenaService(db)
    payload = ArenaChessRunCreate(
        model_id="mock-chess-legal",
        provider_key="mock",
        task_type="game",
        max_moves=50,
        max_retries=2,
    )
    estimate = service.estimate_dry_run(payload)
    # 50 moves * (1 + 2 retries) = 150 upper bound calls
    assert estimate.estimated_calls == 150
    assert estimate.max_moves == 50
    assert estimate.max_retries_per_move == 2


def test_arena_api_routes(client):
    # 1. Status
    res_status = client.get("/api/arena/chess/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "stockfish_available" in status_data
    assert "default_config" in status_data

    # 2. Dry run endpoint
    res_dry = client.post(
        "/api/arena/chess/dry-run",
        json={
            "model_id": "mock-chess-legal",
            "provider_key": "mock",
            "task_type": "game",
            "max_moves": 20,
            "max_retries": 1,
            "dry_run": True,
        },
    )
    assert res_dry.status_code == 200
    dry_data = res_dry.json()
    assert dry_data["estimated_calls"] == 40

    # 3. Runs endpoint with dry_run=True
    res_run_dry = client.post(
        "/api/arena/chess/runs",
        json={
            "model_id": "mock-chess-legal",
            "provider_key": "mock",
            "task_type": "game",
            "max_moves": 10,
            "max_retries": 1,
            "dry_run": True,
        },
    )
    assert res_run_dry.status_code == 200
    assert res_run_dry.json()["estimated_calls"] == 20

    # 4. Live execution of a bounded 2-move arena game
    res_exec = client.post(
        "/api/arena/chess/runs",
        json={
            "model_id": "mock-chess-legal",
            "provider_key": "mock",
            "task_type": "game",
            "max_moves": 2,
            "max_retries": 1,
            "dry_run": False,
        },
    )
    assert res_exec.status_code == 200
    run_data = res_exec.json()
    assert run_data["status"] == "completed"
    assert "summary" in run_data
    assert run_data["summary"]["legal_move_rate"] == 1.0
    run_id = run_data["id"]

    # 5. List runs
    res_list = client.get("/api/arena/chess/runs")
    assert res_list.status_code == 200
    runs = res_list.json()
    assert any(r["id"] == run_id for r in runs)

    # 6. Get run details with moves
    res_get = client.get(f"/api/arena/chess/runs/{run_id}")
    assert res_get.status_code == 200
    detailed = res_get.json()
    assert detailed["id"] == run_id
    assert len(detailed["moves"]) > 0

    # 7. Summary
    res_sum = client.get("/api/arena/chess/summary")
    assert res_sum.status_code == 200
    summary_data = res_sum.json()
    assert summary_data["total_runs"] >= 1
    assert summary_data["completed_games"] >= 1
