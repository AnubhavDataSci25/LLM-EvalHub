"""Recommendation scoring: transparent, constrained and never over-claiming."""

from __future__ import annotations

from app.services.recommendation_service import PROFILES, RecommendationService, _minmax


def test_minmax_helper_normalisation():
    assert _minmax({"a": 1.0, "b": 3.0, "c": 2.0}) == {"a": 0.0, "b": 1.0, "c": 0.5}
    assert _minmax({"a": 0.5, "b": 0.5}) == {"a": 1.0, "b": 1.0}


def test_quality_metrics_keep_their_magnitude():
    """A 0.90 vs 0.88 gap must not score the same as 0.90 vs 0.30."""
    close = RecommendationService._rank(
        [_candidate("p/a", 0.90, 0.90, 500), _candidate("p/b", 0.88, 0.88, 500)],
        {"correctness": 1.0},
    )
    wide = RecommendationService._rank(
        [_candidate("p/a", 0.90, 0.90, 500), _candidate("p/b", 0.30, 0.30, 500)],
        {"correctness": 1.0},
    )
    assert close[0]["weighted_score"] - close[1]["weighted_score"] < 0.05
    assert wide[0]["weighted_score"] - wide[1]["weighted_score"] > 0.5


def _candidate(key, correctness, faithfulness, latency, sample=20):
    return {
        "key": key,
        "provider": key.split("/")[0],
        "model": key.split("/")[1],
        "label": key,
        "cases": sample,
        "sample_size": sample,
        "metrics": {"correctness": correctness, "faithfulness": faithfulness},
        "metric_detail": {},
        "avg_latency_ms": latency,
        "p95_latency_ms": latency,
        "failure_rate": 0.1,
        "error_rate": 0.0,
        "runs": ["run_1"],
    }


def test_quality_profile_prefers_accuracy_over_speed():
    candidates = [
        _candidate("p/accurate-slow", 0.95, 0.93, 3000),
        _candidate("p/fast-weak", 0.62, 0.60, 300),
    ]
    ranked = RecommendationService._rank(candidates, PROFILES["quality"])
    assert ranked[0]["key"] == "p/accurate-slow"


def test_latency_profile_can_flip_the_ranking():
    candidates = [
        _candidate("p/accurate-slow", 0.90, 0.90, 5000),
        _candidate("p/fast-decent", 0.80, 0.80, 200),
    ]
    ranked = RecommendationService._rank(candidates, PROFILES["latency"])
    assert ranked[0]["key"] == "p/fast-decent"


def test_latency_is_inverted_before_weighting():
    candidates = [_candidate("p/a", 0.8, 0.8, 100), _candidate("p/b", 0.8, 0.8, 5000)]
    ranked = RecommendationService._rank(candidates, {"latency": 1.0})
    assert ranked[0]["key"] == "p/a"
    assert ranked[0]["score_breakdown"]["latency"]["normalized"] == 1.0


def test_score_breakdown_is_explainable():
    ranked = RecommendationService._rank(
        [_candidate("p/a", 0.9, 0.8, 500), _candidate("p/b", 0.5, 0.4, 900)],
        PROFILES["balanced"],
    )
    breakdown = ranked[0]["score_breakdown"]
    assert set(breakdown) <= set(PROFILES["balanced"])
    for entry in breakdown.values():
        assert {"raw", "normalized", "weight", "contribution"} <= set(entry)
    assert 0.0 <= ranked[0]["weighted_score"] <= 1.0


def test_candidates_without_measured_metrics_are_excluded():
    blank = _candidate("p/unmeasured", 0, 0, None)
    blank["metrics"] = {}
    ranked = RecommendationService._rank([blank], PROFILES["balanced"])
    assert ranked == []
    assert "excluded_reason" in blank


def test_caveats_flag_small_samples_and_single_candidates():
    winner = _candidate("p/a", 0.9, 0.9, 500, sample=4)
    winner["metric_detail"] = {"correctness": {"kinds": ["deterministic"], "judge_models": []}}
    caveats = RecommendationService._caveats(winner, [winner], [], [], _Request())
    text = " ".join(caveats).lower()
    assert "sample size is small" in text
    assert "fewer than two models" in text
    assert "not a general statement" in text


def test_top_two_tied_caveat_added_when_statistically_indistinguishable():
    winner = _candidate("p/a", 0.90, 0.90, 500, sample=15)
    runner_up = _candidate("p/b", 0.89, 0.89, 510, sample=15)
    winner["metric_detail"] = {"correctness": {"kinds": ["deterministic"], "judge_models": []}}
    tie_note = "The top two models are statistically indistinguishable on this data (p=0.4500, 95% CI [-0.020, 0.040])."
    caveats = RecommendationService._caveats(winner, [winner, runner_up], [], [], _Request(), top_two_note=tie_note)
    assert any("statistically indistinguishable" in c for c in caveats)


class _Request:
    max_latency_ms = None
    min_faithfulness = None
    min_correctness = None
    max_failure_rate = None
    providers: list[str] = []
    min_sample_size = 3
