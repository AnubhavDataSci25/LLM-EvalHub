"""Tests for Counterfactual Failure Attribution."""

from __future__ import annotations

import pytest

from app.evaluation.attribution import (
    CONDITION_ORACLE_CONTEXT,
    VERDICT_GENERATION_CAUSED,
    VERDICT_NOT_ATTRIBUTABLE,
    VERDICT_NOT_CONTEXT_DEPENDENT,
    VERDICT_PARAMETRIC_KNOWLEDGE,
    VERDICT_RETRIEVAL_CAUSED,
    ConditionExecutionResult,
    aggregate_condition_trials,
    compute_attribution,
    evaluate_trial_pass,
)
from app.evaluation.failure_detector import FailureThresholds
from app.providers.mock import MockProvider

# ===========================================================================
# 1. Unit Tests for Pure Attribution Rules
# ===========================================================================

def test_evaluate_trial_pass_thresholds():
    th = FailureThresholds(correctness=0.5, faithfulness=0.6)

    # Passes both
    assert evaluate_trial_pass({"correctness": 0.8, "faithfulness": 0.9}, th, answer="Valid answer")

    # Fails correctness
    assert not evaluate_trial_pass({"correctness": 0.3, "faithfulness": 0.9}, th, answer="Valid answer")

    # Fails faithfulness
    assert not evaluate_trial_pass({"correctness": 0.8, "faithfulness": 0.4}, th, answer="Valid answer")

    # Error present fails regardless of scores
    assert not evaluate_trial_pass({"correctness": 1.0}, th, error="timeout", answer="Valid answer")

    # Empty answer fails
    assert not evaluate_trial_pass({"correctness": 1.0}, th, answer="")


def test_aggregate_condition_trials():
    th = FailureThresholds(correctness=0.5)

    trials = [
        ConditionExecutionResult(condition="oracle_context", repeat_index=0, generated_answer="Ans 1", scores={"correctness": 0.8}),
        ConditionExecutionResult(condition="oracle_context", repeat_index=1, generated_answer="Ans 2", scores={"correctness": 0.2}),
        ConditionExecutionResult(condition="oracle_context", repeat_index=2, generated_answer="Ans 3", scores={"correctness": 0.9}),
    ]

    agg = aggregate_condition_trials("oracle_context", trials, th)
    assert agg.repeats == 3
    assert agg.clean_runs == 3
    assert agg.pass_count == 2
    assert agg.pass_rate == pytest.approx(0.6667, rel=1e-3)
    assert agg.passed is True
    assert agg.avg_scores["correctness"] == pytest.approx(0.6333, rel=1e-3)


def test_attribution_rule_retrieval_caused():
    outcome = compute_attribution(
        original_pass=False,
        oracle_pass=True,
        no_context_pass=False,
        has_gold_context=True,
        repeats=1,
    )
    assert outcome.verdict == VERDICT_RETRIEVAL_CAUSED
    assert outcome.confidence <= 0.95
    assert "retrieval was the bottleneck" in outcome.reason.lower()
    assert any("ORIGINAL failed, but ORACLE_CONTEXT passed" in e for e in outcome.evidence)


def test_attribution_rule_generation_caused():
    outcome = compute_attribution(
        original_pass=False,
        oracle_pass=False,
        no_context_pass=False,
        has_gold_context=True,
        repeats=1,
    )
    assert outcome.verdict == VERDICT_GENERATION_CAUSED
    assert outcome.confidence <= 0.95
    assert "generation bottleneck" in outcome.reason.lower()


def test_attribution_rule_parametric_knowledge():
    outcome = compute_attribution(
        original_pass=False,
        oracle_pass=False,
        no_context_pass=True,
        has_gold_context=True,
        repeats=1,
    )
    assert outcome.verdict == VERDICT_PARAMETRIC_KNOWLEDGE
    assert "context-ignoring" in outcome.reason.lower()


def test_attribution_rule_not_context_dependent():
    outcome = compute_attribution(
        original_pass=True,
        oracle_pass=True,
        no_context_pass=True,
        has_gold_context=True,
        repeats=1,
    )
    assert outcome.verdict == VERDICT_NOT_CONTEXT_DEPENDENT
    assert "parametric knowledge" in outcome.reason.lower()


def test_attribution_missing_gold_context_returns_not_attributable():
    outcome = compute_attribution(
        original_pass=False,
        oracle_pass=True,
        no_context_pass=False,
        has_gold_context=False,
    )
    assert outcome.verdict == VERDICT_NOT_ATTRIBUTABLE
    assert outcome.confidence == 0.0
    assert "missing gold context" in outcome.reason.lower()


def test_attribution_provider_error_returns_not_attributable():
    outcome = compute_attribution(
        original_pass=False,
        oracle_pass=False,
        no_context_pass=False,
        has_gold_context=True,
        condition_errors={CONDITION_ORACLE_CONTEXT: "rate_limited: 429 Too Many Requests"},
    )
    assert outcome.verdict == VERDICT_NOT_ATTRIBUTABLE
    assert outcome.confidence == 0.0
    assert "provider error" in outcome.reason.lower()


def test_attribution_confidence_capping_and_repeats():
    # N=1 states single trial
    outcome_n1 = compute_attribution(
        original_pass=False,
        oracle_pass=True,
        no_context_pass=False,
        has_gold_context=True,
        repeats=1,
    )
    assert outcome_n1.confidence == 0.80
    assert any("single trial (N=1)" in e for e in outcome_n1.evidence)

    # N=5 capped at 0.95
    outcome_n5 = compute_attribution(
        original_pass=False,
        oracle_pass=True,
        no_context_pass=False,
        has_gold_context=True,
        repeats=5,
    )
    assert outcome_n5.confidence <= 0.95
    assert outcome_n5.confidence == 0.95
    assert any("N=5 trials per condition" in e for e in outcome_n5.evidence)


# ===========================================================================
# 2. Mock Provider Behaviour Extensions
# ===========================================================================

@pytest.mark.asyncio
async def test_mock_provider_oracle_only_behaviour():
    prov = MockProvider()

    # With gold context, oracle_only succeeds
    gold_prompt = "Context: The gold policy states 30 days refund.\n\nQuestion: What is the refund policy?"
    res_gold = await prov.generate(gold_prompt, model="mock-oracle-only")
    assert "30 days" in res_gold.text or "gold" in res_gold.text.lower()

    # With non-gold distractor context, oracle_only fails
    distractor_prompt = "Context: General company shipping rules and delivery terms.\n\nQuestion: What is the refund policy?"
    res_dist = await prov.generate(distractor_prompt, model="mock-oracle-only")
    assert "Irrelevant" in res_dist.text or "unable" in res_dist.text.lower()


@pytest.mark.asyncio
async def test_mock_provider_always_fail_behaviour():
    prov = MockProvider()
    res = await prov.generate("Context: Gold context 30 days.\n\nQuestion: Refund?", model="mock-always-fail")
    assert "Incorrect" in res.text or "fabricated" in res.text.lower()


@pytest.mark.asyncio
async def test_mock_provider_parametric_behaviour():
    prov = MockProvider()
    # Without context, parametric answers correctly
    res_no_ctx = await prov.generate("Question: What is the refund policy?", model="mock-parametric")
    assert "expected answer is 30 days" in res_no_ctx.text.lower()

    # With context, it gets distracted and fails
    res_with_ctx = await prov.generate("Context: Some context.\n\nQuestion: What is the refund policy?", model="mock-parametric")
    assert "Confused by context" in res_with_ctx.text


# ===========================================================================
# 3. Integration & API Flow Tests
# ===========================================================================

def _create_rag_experiment_with_failure(client, model="mock-oracle-only"):
    cases = [
        {
            "question": "What is the return window?",
            "ground_truth": "30 days from purchase.",
            "context": "Gold context: Items may be returned within 30 days from purchase.",
            "expected_sources": ["Gold context: Items may be returned within 30 days from purchase."],
        }
    ]
    ds_res = client.post("/api/datasets/import", json={"name": "AttributionDS", "rows": cases})
    assert ds_res.status_code == 201
    ds_id = ds_res.json()["id"]

    # Ingest document for RAG
    doc_res = client.post(
        "/api/documents/upload",
        files={"file": ("policy.txt", b"General shipping details: deliveries take 3 business days.", "text/plain")},
        data={"collection": "attr_test"},
    )
    assert doc_res.status_code in {200, 201}
    doc_id = doc_res.json()["id"]

    idx_res = client.post(
        "/api/documents/index",
        json={"document_ids": [doc_id], "collection": "attr_test"},
    )
    assert idx_res.status_code == 200

    exp_payload = {
        "name": "AttributionExp",
        "dataset_id": ds_id,
        "models": [{"provider": "mock", "model": model}],
        "metrics": ["correctness"],
        "rag": {
            "enabled": True,
            "collection": "attr_test",
            "top_k": 2,
        },
    }
    exp_res = client.post("/api/evaluations/run", json={"experiment": exp_payload})
    assert exp_res.status_code == 202
    run_id = exp_res.json()["id"]

    # Fetch failure
    failures = client.get(f"/api/failures?run_id={run_id}").json()["items"]
    assert len(failures) > 0, "Expected a failure to be detected."
    return failures[0], run_id, exp_payload["name"]


def test_failure_attribution_api_flow(client):
    failure, run_id, _ = _create_rag_experiment_with_failure(client, model="mock-oracle-only")
    failure_id = failure["id"]

    # 1. Run counterfactual attribution
    att_res = client.post(f"/api/failures/{failure_id}/attribution", json={"repeats": 1})
    assert att_res.status_code == 200
    att = att_res.json()

    assert att["failure_id"] == failure_id
    assert att["verdict"] == VERDICT_RETRIEVAL_CAUSED
    assert att["confidence"] == 0.80
    assert len(att["conditions"]) >= 3  # original, oracle_context, no_context
    assert att["status"] == "completed"

    # 2. GET /failures/{id}/attribution returns the stored attribution
    get_res = client.get(f"/api/failures/{failure_id}/attribution")
    assert get_res.status_code == 200
    got = get_res.json()
    assert got["id"] == att["id"]
    assert got["verdict"] == VERDICT_RETRIEVAL_CAUSED

    # 3. GET /failures/{id} includes attribution metadata and counterfactual detector
    fail_detail = client.get(f"/api/failures/{failure_id}").json()
    assert fail_detail["detector"] == "counterfactual"
    assert fail_detail.get("attribution_confirmed") is True
    assert fail_detail.get("attribution")["verdict"] == VERDICT_RETRIEVAL_CAUSED


def test_attribution_idempotency(client):
    failure, _, _ = _create_rag_experiment_with_failure(client, model="mock-oracle-only")
    failure_id = failure["id"]

    # First run
    r1 = client.post(f"/api/failures/{failure_id}/attribution", json={"repeats": 1})
    assert r1.status_code == 200
    id1 = r1.json()["id"]

    # Second run replaces previous record without duplicate key error
    r2 = client.post(f"/api/failures/{failure_id}/attribution", json={"repeats": 2})
    assert r2.status_code == 200
    id2 = r2.json()["id"]

    assert id1 != id2
    assert r2.json()["repeats"] == 2


def test_batch_attribution_dry_run_and_caps(client):
    failure, run_id, _ = _create_rag_experiment_with_failure(client, model="mock-oracle-only")
    exp_id = failure["experiment_id"]

    # Dry-run returns call estimate without executing
    dry_res = client.post(
        f"/api/experiments/{exp_id}/attribution",
        json={"dry_run": True, "max_cases": 10, "repeats": 3},
    )
    assert dry_res.status_code == 200
    dry = dry_res.json()
    assert dry["dry_run"] is True
    assert dry["repeats"] == 3
    # 2 conditions * 3 repeats = 6 calls per target case
    assert dry["estimated_provider_calls"] == dry["target_cases"] * 2 * 3

    # Summary endpoint
    sum_res = client.get(f"/api/experiments/{exp_id}/attribution/summary")
    assert sum_res.status_code == 200
    summary = sum_res.json()
    assert "verdict_counts" in summary
    assert "retrieval_share" in summary
    assert "generation_share" in summary


def test_diagnosis_and_recommendation_incorporate_attribution(client, db):
    failure, run_id, _ = _create_rag_experiment_with_failure(client, model="mock-oracle-only")
    failure_id = failure["id"]

    # Run attribution
    client.post(f"/api/failures/{failure_id}/attribution", json={"repeats": 1})

    # Run AI diagnosis
    diag_res = client.post(f"/api/failures/{failure_id}/diagnose", json={"force": True})
    assert diag_res.status_code == 200
    diag = diag_res.json()["diagnosis"]

    assert diag["engine"] == "counterfactual"
    assert diag["attribution_confirmed"] is True
    assert "retrieval was the bottleneck" in diag["root_cause"].lower()

    # Recommendations caveat check
    rec_res = client.post("/api/recommendations", json={"run_ids": [run_id], "profile": "balanced", "min_sample_size": 1})
    assert rec_res.status_code == 201
    rec = rec_res.json()
    assert any("retrieval-caused" in c.lower() for c in rec["caveats"])

    # Reports attribution block check
    rep_res = client.post("/api/reports", json={"run_id": run_id, "title": "Attribution Report"})
    assert rep_res.status_code == 201
    rep = rep_res.json()["content"]
    assert "attribution" in rep
    assert rep["attribution"]["total_attributed"] >= 1
    assert rep["attribution"]["retrieval_caused_share"] > 0
    assert len(rep["attribution"]["limitations"]) > 0
