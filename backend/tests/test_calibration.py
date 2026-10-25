"""Tests for judge calibration: Cohen's kappa, intervals, probes, and API flow."""

import numpy as np

from app.evaluation.calibration import (
    cohens_kappa,
    discretise,
    flip_rate,
    interpret_kappa,
    judge_bias_summary,
    kappa_interval,
    wilson_interval,
)
from app.models.experiment import EvaluationResult, MetricResult
from app.services.calibration_service import CalibrationService


def test_discretise_thresholds():
    assert discretise(0.0) == 0
    assert discretise(0.20) == 0
    assert discretise(0.339) == 0
    assert discretise(0.34) == 1
    assert discretise(0.50) == 1
    assert discretise(0.669) == 1
    assert discretise(0.67) == 2
    assert discretise(1.0) == 2
    assert discretise(None) == 0


def test_cohens_kappa_perfect_agreement():
    a = [0, 1, 2, 0, 1, 2, 0, 1, 2]
    b = [0, 1, 2, 0, 1, 2, 0, 1, 2]
    res = cohens_kappa(a, b)
    assert res["kappa"] == 1.0
    assert res["observed_agreement"] == 1.0
    assert res["n"] == 9
    assert res["confusion_matrix"] == [[3, 0, 0], [0, 3, 0], [0, 0, 3]]


def test_cohens_kappa_hand_computed_2x2():
    # 50 cases: C_00=20, C_01=5, C_10=10, C_11=15
    # Po = 35/50 = 0.70; Pe = (25*30 + 25*20)/2500 = 0.50; Kappa = (0.7-0.5)/(1-0.5) = 0.400
    a = [0] * 20 + [0] * 5 + [1] * 10 + [1] * 15
    b = [0] * 20 + [1] * 5 + [0] * 10 + [1] * 15
    res = cohens_kappa(a, b)
    assert round(res["kappa"], 3) == 0.400
    assert round(res["observed_agreement"], 2) == 0.70
    assert round(res["expected_agreement"], 2) == 0.50


def test_cohens_kappa_chance_level():
    rng = np.random.default_rng(42)
    a = rng.integers(0, 3, size=600).tolist()
    b = rng.integers(0, 3, size=600).tolist()
    res = cohens_kappa(a, b)
    assert res["kappa"] is not None
    assert abs(res["kappa"]) < 0.10


def test_cohens_kappa_degenerate_returns_none():
    # All ratings identical -> expected agreement = 1.0
    a = [1, 1, 1, 1, 1]
    b = [1, 1, 1, 1, 1]
    res = cohens_kappa(a, b)
    assert res["kappa"] is None
    assert res["expected_agreement"] == 1.0


def test_cohens_kappa_quadratic_weighting_penalises_distance():
    a = [0, 1, 2, 0, 1, 2, 0, 1, 2, 0]
    # Small disagreement: one 2-vs-1 (distance 1)
    b_small = [0, 1, 2, 0, 1, 2, 0, 1, 1, 0]
    # Large disagreement: one 2-vs-0 (distance 2)
    b_large = [0, 1, 2, 0, 1, 2, 0, 1, 0, 0]

    k_quad_small = cohens_kappa(a, b_small, weights="quadratic")["kappa"]
    k_quad_large = cohens_kappa(a, b_large, weights="quadratic")["kappa"]
    assert k_quad_small is not None and k_quad_large is not None
    assert k_quad_small > k_quad_large


def test_kappa_interval_none_for_small_n_and_reproducible():
    small_a = [0, 1, 2, 0, 1]
    small_b = [0, 1, 2, 0, 1]
    assert kappa_interval(small_a, small_b, n_resamples=100) is None

    # n >= 10
    a = [0, 1, 2, 0, 1, 2, 0, 1, 2, 1, 0, 2]
    b = [0, 1, 2, 0, 2, 2, 0, 1, 1, 1, 0, 2]
    ci1 = kappa_interval(a, b, n_resamples=500, seed=1234)
    ci2 = kappa_interval(a, b, n_resamples=500, seed=1234)
    assert ci1 is not None and ci2 is not None
    assert ci1 == ci2
    low, high = ci1
    assert low <= high


def test_interpret_kappa_bands():
    assert interpret_kappa(-0.2) == "poor"
    assert interpret_kappa(0.15) == "slight"
    assert interpret_kappa(0.20) == "slight"
    assert interpret_kappa(0.21) == "fair"
    assert interpret_kappa(0.40) == "fair"
    assert interpret_kappa(0.41) == "moderate"
    assert interpret_kappa(0.60) == "moderate"
    assert interpret_kappa(0.61) == "substantial"
    assert interpret_kappa(0.80) == "substantial"
    assert interpret_kappa(0.85) == "almost perfect"
    assert interpret_kappa(1.0) == "almost perfect"
    assert interpret_kappa(None) == "uncalibrated"


def test_flip_rate_and_wilson_interval():
    low, high = wilson_interval(10, 100, z=1.96)
    assert 0.05 < low < 0.06
    assert 0.16 < high < 0.18

    orig = [0, 1, 2, 0, 1, 2]
    probed = [0, 2, 2, 0, 1, 0]  # indices 1 and 5 flipped (2 of 6)
    res = flip_rate(orig, probed)
    assert res["n"] == 6
    assert res["flips"] == 2
    assert round(res["flip_rate"], 3) == 0.333


def test_judge_bias_summary():
    human = [1, 2, 0, 1]
    judge = [2, 2, 1, 0]
    # diffs = [1, 0, 1, -1] -> mean 0.25, over=2/4 (0.5), under=1/4 (0.25), exact=1/4 (0.25)
    bias = judge_bias_summary(human, judge)
    assert bias["mean_signed_error"] == 0.25
    assert bias["over_scoring_share"] == 0.5
    assert bias["under_scoring_share"] == 0.25
    assert bias["exact_agreement_share"] == 0.25


def _make_run(client, n_cases=12, judge_provider="mock", judge_model="mock-judge"):
    rows = [
        {"question": f"Q{i}?", "ground_truth": f"A{i}.", "context": f"C{i}."}
        for i in range(n_cases)
    ]
    ds_res = client.post("/api/datasets/import", json={"name": f"DS-{n_cases}", "rows": rows})
    assert ds_res.status_code == 201
    ds_id = ds_res.json()["id"]

    exp_payload = {
        "name": f"Exp-{n_cases}",
        "dataset_id": ds_id,
        "models": [{"provider": "mock", "model": "mock-extractive"}],
        "metrics": ["correctness"],
    }
    if judge_provider and judge_model:
        exp_payload["judge"] = {"provider": judge_provider, "model": judge_model}

    run_res = client.post("/api/evaluations/run", json={"experiment": exp_payload})
    assert run_res.status_code == 202
    return run_res.json()["id"]


def test_label_upsert_idempotent(client):
    run_id = _make_run(client, n_cases=3)
    results = client.get(f"/api/evaluations/{run_id}/results").json()["items"]
    res_id = results[0]["id"]

    # First label
    r1 = client.post(
        "/api/calibration/labels",
        json={"result_id": res_id, "metric": "correctness", "label": 2, "annotator": "ann1", "note": "good"},
    )
    assert r1.status_code == 200
    lbl1 = r1.json()
    assert lbl1["label"] == 2
    assert lbl1["note"] == "good"

    # Update same (result, metric, annotator)
    r2 = client.post(
        "/api/calibration/labels",
        json={"result_id": res_id, "metric": "correctness", "label": 1, "annotator": "ann1", "note": "updated"},
    )
    assert r2.status_code == 200
    lbl2 = r2.json()
    assert lbl2["id"] == lbl1["id"]
    assert lbl2["label"] == 1
    assert lbl2["note"] == "updated"

    # Different annotator creates new label
    r3 = client.post(
        "/api/calibration/labels",
        json={"result_id": res_id, "metric": "correctness", "label": 0, "annotator": "ann2"},
    )
    assert r3.status_code == 200
    lbl3 = r3.json()
    assert lbl3["id"] != lbl1["id"]


def test_insufficient_labels_returns_status(client):
    run_id = _make_run(client, n_cases=12)
    results = client.get(f"/api/evaluations/{run_id}/results").json()["items"]

    # Label only 5 cases (< 10)
    for i in range(5):
        client.post(
            "/api/calibration/labels",
            json={"result_id": results[i]["id"], "metric": "correctness", "label": 2},
        )

    cal_res = client.post(
        "/api/calibration/run",
        json={"run_id": run_id, "metric": "correctness", "judge_provider": "mock", "judge_model": "mock-judge"},
    )
    assert cal_res.status_code == 200
    cal = cal_res.json()
    assert cal["status"] == "insufficient_labels"
    assert cal["n_labels"] == 5
    assert "kappa" not in cal["agreement"] or cal["agreement"].get("kappa") is None


def test_unlabelled_queue_hides_judge_score(client):
    run_id = _make_run(client, n_cases=3)
    queue = client.get(f"/api/calibration/queue?run_id={run_id}&metric=correctness").json()
    assert len(queue) == 3
    for item in queue:
        assert item["question"].startswith("Q")
        assert item["expected_answer"].startswith("A")
        assert item["generated_answer"]
        # Crucially: judge score is hidden
        assert "normalized_score" not in item
        assert "score" not in item
        assert "judge_score" not in item


def test_deterministic_only_returns_no_judge_scores(client):
    # Run with no judge configured (deterministic only)
    run_id = _make_run(client, n_cases=12, judge_provider=None, judge_model=None)
    results = client.get(f"/api/evaluations/{run_id}/results").json()["items"]

    for i in range(12):
        client.post(
            "/api/calibration/labels",
            json={"result_id": results[i]["id"], "metric": "correctness", "label": 2},
        )

    cal_res = client.post(
        "/api/calibration/run",
        json={"run_id": run_id, "metric": "correctness"},
    )
    assert cal_res.status_code == 200
    cal = cal_res.json()
    assert cal["status"] == "no_judge_scores"


def test_unconfigured_judge_returns_judge_unavailable(client):
    run_id = _make_run(client, n_cases=12)
    results = client.get(f"/api/evaluations/{run_id}/results").json()["items"]

    for i in range(12):
        client.post(
            "/api/calibration/labels",
            json={"result_id": results[i]["id"], "metric": "correctness", "label": 2},
        )

    # Calling with unconfigured judge provider does not raise, returns judge_unavailable
    cal_res = client.post(
        "/api/calibration/run",
        json={
            "run_id": run_id,
            "metric": "correctness",
            "judge_provider": "unconfigured_prov",
            "judge_model": "some-model",
        },
    )
    assert cal_res.status_code == 200
    cal = cal_res.json()
    assert cal["status"] == "judge_unavailable"


def test_self_preference_probe():

    # Construct mock pairs: same-family (mock vs mock) and other-family (groq vs mock)
    same_res = EvaluationResult(id="r1", provider="mock", model="mock-extractive")
    same_mr = MetricResult(id="m1", result_id="r1", metric="correctness", kind="llm_judge", normalized_score=0.9)

    other_res = EvaluationResult(id="r2", provider="groq", model="llama-3.1-8b")
    other_mr = MetricResult(id="m2", result_id="r2", metric="correctness", kind="llm_judge", normalized_score=0.5)

    pairs = [(same_res, same_mr), (other_res, other_mr)]

    service = CalibrationService(None)  # db not needed for pure probe
    probe = service._probe_self_preference(pairs, judge_provider="mock", judge_model="mock-judge")

    assert probe["name"] == "self_preference"
    assert probe["n_same_family"] == 1
    assert probe["n_other_family"] == 1
    assert probe["mean_same_family"] == 0.9
    assert probe["mean_other_family"] == 0.5
    assert len(probe["warnings"]) > 0
    assert "self-preference" in probe["interpretation"].lower()


def test_end_to_end_mock_judge_calibration(client):
    rows = [
        {"question": f"Question {i}?", "ground_truth": f"Answer {i}.", "context": f"Context for {i}."}
        for i in range(12)
    ]
    res = client.post("/api/datasets/import", json={"name": "Calib DS", "rows": rows})
    assert res.status_code == 201
    dataset_id = res.json()["id"]

    # Run evaluation with mock judge
    run_res = client.post(
        "/api/evaluations/run",
        json={
            "experiment": {
                "name": "Judge Experiment",
                "dataset_id": dataset_id,
                "models": [{"provider": "mock", "model": "mock-extractive"}],
                "judge": {"provider": "mock", "model": "mock-judge"},
                "metrics": ["correctness"],
            }
        },
    )
    assert run_res.status_code == 202
    run_id = run_res.json()["id"]

    # Check labelling queue (blind, hides judge score)
    queue_res = client.get(f"/api/calibration/queue?run_id={run_id}&metric=correctness&limit=20")
    assert queue_res.status_code == 200
    queue = queue_res.json()
    assert len(queue) == 12
    for item in queue:
        assert "normalized_score" not in item
        assert "score" not in item

    # Label all 12 cases
    labels_to_assign = [2, 1, 0, 2, 2, 1, 0, 2, 1, 0, 2, 1]
    for idx, item in enumerate(queue):
        label_res = client.post(
            "/api/calibration/labels",
            json={
                "result_id": item["result_id"],
                "metric": "correctness",
                "label": labels_to_assign[idx],
                "annotator": "expert_1",
                "note": f"Annotation {idx}",
            },
        )
        assert label_res.status_code == 200

    # Execute calibration run
    cal_res = client.post(
        "/api/calibration/run",
        json={
            "run_id": run_id,
            "metric": "correctness",
            "judge_provider": "mock",
            "judge_model": "mock-judge",
            "run_probes": True,
        },
    )
    assert cal_res.status_code == 200
    cal_data = cal_res.json()
    assert cal_data["status"] == "completed"
    assert cal_data["n_labels"] == 12
    assert cal_data["agreement"]["kappa"] is not None
    assert cal_data["agreement"]["interval"] is not None
    assert len(cal_data["agreement"]["confusion_matrix"]) == 3
    assert "order_swap" in cal_data["probes"]
    assert "verbosity_padding" in cal_data["probes"]
    assert "self_preference" in cal_data["probes"]

    # Test reliability endpoint
    rel_res = client.get("/api/calibration/reliability?provider=mock&model=mock-judge&metric=correctness")
    assert rel_res.status_code == 200
    rel_data = rel_res.json()
    assert rel_data["calibrated"] is True
    assert rel_data["kappa"] == cal_data["agreement"]["kappa"]
    assert rel_data["n_labels"] == 12

    # Check dashboard KPI has judge_calibration
    dash_res = client.get("/api/dashboard")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert dash_data["judge_calibration"]["calibrated"] is True
    assert dash_data["judge_calibration"]["kappa"] == cal_data["agreement"]["kappa"]
    assert dash_data["judge_calibration"]["n_labels"] == 12
