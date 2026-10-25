"""End-to-end API test of the full product loop.

    dataset -> experiment -> evaluation -> results -> failures -> diagnosis
      -> follow-up experiment -> re-run -> before/after -> recommendation -> report

Runs entirely on the deterministic test provider, so it is reproducible and
never touches a paid API.
"""

from __future__ import annotations

from tests.conftest import wait_for_run


def _install_dataset(client, rows) -> str:
    response = client.post(
        "/api/datasets/import",
        json={"name": "API flow dataset", "domain": "policy", "rows": rows},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_health_and_metadata(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["providers_total"] >= 6

    metrics = client.get("/api/meta/metrics").json()
    keys = {m["key"] for m in metrics["metrics"]}
    assert {"correctness", "faithfulness", "answer_relevance", "context_precision",
            "context_recall", "latency"} <= keys

    failures = client.get("/api/meta/failure-types").json()
    assert {"hallucination", "poor_retrieval", "timeout"} <= {
        f["key"] for f in failures["failure_types"]
    }


def test_providers_never_expose_secrets(client, monkeypatch):
    """A configured credential must never appear anywhere in an API response."""
    from app.core.config import settings

    sentinel = "sk-do-not-leak-this-value-123456"
    monkeypatch.setattr(settings, "groq_api_key", sentinel)

    payload = client.get("/api/providers").json()
    body = str(payload)
    assert sentinel not in body
    groq = next(p for p in payload["providers"] if p["key"] == "groq")
    assert groq["configured"] is True  # reported as configured, without the value
    assert "api_key" not in groq  # the key itself is never a response field
    assert any(p["key"] == "mock" and p["configured"] for p in payload["providers"])


def test_dataset_crud(client, sample_rows):
    dataset_id = _install_dataset(client, sample_rows)

    detail = client.get(f"/api/datasets/{dataset_id}").json()
    assert detail["row_count"] == 3
    assert detail["has_ground_truth"] and detail["has_context"]
    assert detail["validation_report"]["valid"] is True

    added = client.post(
        f"/api/datasets/{dataset_id}/cases",
        json={"question": "Added question?", "ground_truth": "Added answer."},
    )
    assert added.status_code == 201
    case_id = added.json()["id"]

    updated = client.put(f"/api/datasets/cases/{case_id}", json={"difficulty": "hard"})
    assert updated.json()["difficulty"] == "hard"

    assert client.delete(f"/api/datasets/cases/{case_id}").json()["ok"] is True
    assert client.get(f"/api/datasets/{dataset_id}").json()["row_count"] == 3


def test_invalid_dataset_returns_structured_error(client):
    response = client.post(
        "/api/datasets/import", json={"name": "Broken", "rows": [{"answer": "no question"}]}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"]["errors"][0]["field"] == "question"


def test_experiment_rejects_unconfigured_provider(client, sample_rows):
    dataset_id = _install_dataset(client, sample_rows)
    response = client.post(
        "/api/experiments",
        json={
            "name": "Unconfigured",
            "dataset_id": dataset_id,
            "models": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}],
        },
    )
    assert response.status_code == 422
    assert "not configured" in response.json()["error"]["message"]


def test_full_evaluation_loop(client, sample_rows):
    dataset_id = _install_dataset(client, sample_rows)

    # --- evaluate ---------------------------------------------------------
    started = client.post(
        "/api/evaluations/run",
        json={
            "experiment": {
                "name": "Baseline",
                "dataset_id": dataset_id,
                "models": [
                    {"provider": "mock", "model": "mock-extractive"},
                    {"provider": "mock", "model": "mock-hallucinate"},
                ],
                "metrics": ["correctness", "answer_relevance", "faithfulness", "latency"],
            }
        },
    )
    assert started.status_code == 202
    run_id = started.json()["id"]

    run = wait_for_run(client, run_id)
    assert run["status"] == "completed"
    assert run["completed_units"] == run["total_units"] == 6
    summary = run["summary"]
    assert summary["total_cases"] == 6
    assert summary["metrics"]["correctness"]["sample_size"] > 0

    # --- compare models ---------------------------------------------------
    comparison = client.get(f"/api/compare/models/{run_id}").json()
    assert len(comparison["rows"]) == 2
    extractive = next(r for r in comparison["rows"] if "extractive" in r["model"])
    hallucinating = next(r for r in comparison["rows"] if "hallucinate" in r["model"])
    assert (
        extractive["metrics"]["correctness"]["mean"]
        > hallucinating["metrics"]["correctness"]["mean"]
    ), "the extractive baseline should beat the hallucinating one on identical inputs"

    # --- inspect results --------------------------------------------------
    results = client.get(f"/api/evaluations/{run_id}/results", params={"limit": 50}).json()
    assert results["total"] == 6
    first = results["items"][0]
    assert {"question", "generated_answer", "metrics", "latency_ms"} <= set(first)

    failed_only = client.get(
        f"/api/evaluations/{run_id}/results", params={"failed_only": True}
    ).json()
    assert failed_only["total"] >= 1

    # --- failures + diagnosis --------------------------------------------
    failures = client.get("/api/failures", params={"run_id": run_id}).json()
    assert failures["total"] >= 1
    failure_id = failures["items"][0]["id"]

    diagnosed = client.post(f"/api/failures/{failure_id}/diagnose", json={}).json()
    diagnosis = diagnosed["diagnosis"]
    assert diagnosed["diagnosis_source"] == "heuristic"
    assert diagnosis["root_cause"] and diagnosis["evidence"]
    assert 0 < diagnosis["confidence"] <= 1
    assert all("apply" in s for s in diagnosis["suggestions"])

    detail = client.get(f"/api/failures/{failure_id}").json()
    assert detail["result"]["question"]

    # --- improvement loop -------------------------------------------------
    experiment_id = run["experiment_id"]
    improvement = client.post(
        f"/api/experiments/{experiment_id}/improve",
        json={
            "apply": {"temperature": 0.2, "max_tokens": 256},
            "run_id": run_id,
            "rerun_failed_only": False,
            "auto_run": True,
            "change_summary": "Test change",
        },
    ).json()
    assert improvement["experiment"]["parent_experiment_id"] == experiment_id
    assert improvement["config_diff"], "a follow-up must record what changed"
    followup_run_id = improvement["run_id"]
    followup = wait_for_run(client, followup_run_id)
    assert followup["status"] == "completed"

    # --- before/after -----------------------------------------------------
    outcome = client.get(
        "/api/compare/improvement",
        params={"baseline_run_id": run_id, "followup_run_id": followup_run_id},
    ).json()
    assert outcome["verdict"]["label"] in {"improvement", "regression", "mixed", "not comparable"}
    assert outcome["metric_deltas"]
    for d in outcome["metric_deltas"]:
        assert "ci_low" in d
        assert "ci_high" in d
        assert "p_value" in d
        assert "significance" in d
        assert d["significance"] in {"significant", "not_significant", "underpowered"}

    # Assert unavailable metrics have significance == "not_comparable" rather than a number
    comp_with_unavail = client.post(
        "/api/compare",
        json={"run_ids": [run_id, followup_run_id], "metrics": ["correctness", "context_recall"]},
    ).json()
    cr_delta = next(
        d for d in comp_with_unavail["comparisons"][0]["metric_deltas"] if d["metric"] == "context_recall"
    )
    assert cr_delta["significance"] == "not_comparable"
    assert cr_delta["p_value"] is None

    # Assert pairwise model significance matrix endpoint
    sig_matrix = client.get(f"/api/compare/models/{run_id}/significance?metric=correctness").json()
    assert sig_matrix["run_id"] == run_id
    assert len(sig_matrix["models"]) == 2
    assert len(sig_matrix["pairs"]) == 1
    assert "p_value_adjusted" in sig_matrix["pairs"][0]
    assert sig_matrix["pairs"][0]["significance"] in {"significant", "not_significant", "underpowered"}

    # --- recommendation ---------------------------------------------------
    recommendation = client.post(
        "/api/recommendations",
        json={"use_case": "policy_qa", "profile": "quality", "run_ids": [run_id], "min_sample_size": 1},
    ).json()
    assert recommendation["recommended_model"] == "mock-extractive"
    assert recommendation["evidence"] and recommendation["caveats"]
    assert "not a general statement" in " ".join(recommendation["caveats"]).lower()
    winner = next(c for c in recommendation["candidates"] if c.get("rank") == 1)
    assert winner["score_breakdown"]

    # --- report + exports -------------------------------------------------
    report = client.post(
        "/api/reports", json={"run_id": run_id, "include_failures": True}
    ).json()
    content = report["content"]
    assert content["findings"] and content["next_steps"]
    assert content["dataset"]["case_count"] == 3
    assert content["models_tested"]

    csv_export = client.get(f"/api/reports/{report['id']}/export", params={"format": "csv"})
    assert csv_export.status_code == 200
    assert "generated_answer" in csv_export.text.splitlines()[0]

    json_export = client.get(f"/api/reports/{report['id']}/export", params={"format": "json"})
    assert json_export.status_code == 200


def test_metrics_report_unavailable_instead_of_zero(client):
    """A dataset with no ground truth must not silently score correctness as 0."""
    dataset_id = _install_dataset(
        client, [{"question": "Open ended question with no reference?"}]
    )
    run_id = client.post(
        "/api/evaluations/run",
        json={
            "experiment": {
                "name": "No ground truth",
                "dataset_id": dataset_id,
                "models": [{"provider": "mock", "model": "mock-extractive"}],
                "metrics": ["correctness", "answer_relevance", "latency"],
            }
        },
    ).json()["id"]
    wait_for_run(client, run_id)

    results = client.get(f"/api/evaluations/{run_id}/results").json()["items"]
    correctness = next(m for m in results[0]["metrics"] if m["metric"] == "correctness")
    assert correctness["available"] is False
    assert correctness["normalized_score"] is None
    assert "ground_truth" in correctness["unavailable_reason"]


def test_provider_errors_are_recorded_not_raised(client, sample_rows):
    dataset_id = _install_dataset(client, sample_rows)
    run_id = client.post(
        "/api/evaluations/run",
        json={
            "experiment": {
                "name": "Failing provider",
                "dataset_id": dataset_id,
                "models": [{"provider": "mock", "model": "mock-error"}],
                "metrics": ["correctness", "latency"],
            }
        },
    ).json()["id"]
    run = wait_for_run(client, run_id)

    assert run["status"] == "completed", "a provider failure must not kill the run"
    assert run["summary"]["error_cases"] == 3
    results = client.get(f"/api/evaluations/{run_id}/results").json()["items"]
    assert all(r["status"] == "error" and r["error_kind"] for r in results)
    failures = client.get("/api/failures", params={"run_id": run_id}).json()["items"]
    assert all(f["failure_type"] == "provider_error" for f in failures)


def test_recommendation_requires_measured_results(client):
    response = client.post(
        "/api/recommendations",
        json={"profile": "balanced", "run_ids": ["run_does_not_exist"], "min_sample_size": 1},
    )
    assert response.status_code == 422
    assert "no recommendation" in response.json()["error"]["message"].lower()


def test_404_shape_is_consistent(client):
    response = client.get("/api/datasets/ds_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_two_identical_runs_yield_zero_diff_and_not_significant(client, sample_rows):
    # Need at least min_n (8) cases so it is not flagged as underpowered
    rows = []
    for i in range(10):
        base_row = sample_rows[i % len(sample_rows)]
        rows.append({**base_row, "id": f"tc-ident-{i}", "question": f"Question {i}?"})
    dataset_id = _install_dataset(client, rows)
    started = client.post(
        "/api/evaluations/run",
        json={
            "experiment": {
                "name": "Identical run comparison",
                "dataset_id": dataset_id,
                "models": [{"provider": "mock", "model": "mock-extractive"}],
                "metrics": ["correctness"],
            }
        },
    ).json()
    run_id = started["id"]
    wait_for_run(client, run_id)

    outcome = client.get(
        "/api/compare/improvement",
        params={"baseline_run_id": run_id, "followup_run_id": run_id},
    ).json()
    correctness_delta = next(d for d in outcome["metric_deltas"] if d["metric"] == "correctness")
    assert correctness_delta["delta"] == 0.0
    assert correctness_delta["significance"] == "not_significant"
    assert correctness_delta["ci_low"] == 0.0
    assert correctness_delta["ci_high"] == 0.0
    assert correctness_delta["p_value"] == 1.0


def test_calibration_api_flow(client, sample_rows):
    dataset_id = _install_dataset(client, sample_rows)
    started = client.post(
        "/api/evaluations/run",
        json={
            "experiment": {
                "name": "Judge Eval for Flow",
                "dataset_id": dataset_id,
                "models": [{"provider": "mock", "model": "mock-extractive"}],
                "judge": {"provider": "mock", "model": "mock-judge"},
                "metrics": ["correctness"],
            }
        },
    ).json()
    run_id = started["id"]
    wait_for_run(client, run_id)

    # Queue returns blind unlabelled cases
    queue = client.get(f"/api/calibration/queue?run_id={run_id}&metric=correctness").json()
    assert len(queue) == len(sample_rows)
    for q in queue:
        assert "score" not in q and "normalized_score" not in q

    # Post a label
    label_res = client.post(
        "/api/calibration/labels",
        json={
            "result_id": queue[0]["result_id"],
            "metric": "correctness",
            "label": 2,
            "annotator": "reviewer_a",
            "note": "accurate answer",
        },
    )
    assert label_res.status_code == 200
    assert label_res.json()["annotator"] == "reviewer_a"

    # List labels
    labels = client.get(f"/api/calibration/labels?run_id={run_id}&metric=correctness").json()
    assert len(labels) == 1
