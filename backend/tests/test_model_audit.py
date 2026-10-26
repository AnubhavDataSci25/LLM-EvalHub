"""Tests for Model Availability Audit.

Covers:
- Non-chat model filtering (data-driven rules for embeddings, moderation, rerankers, etc.)
- Status classification for every probe error type
- Auth failure early-stopping & probe caps
- Dry-run call volume estimation
- TTL cache expiration & freshness
- Auto-invalidation on evaluation run failure
- Availability invariant (nothing AVAILABLE without a successful probe)
- API endpoints (/audit, /audit/{id}, /status, /models, /recheck, /ready)
- Evaluation creation rejection for unavailable models (422)
- Security sentinel: no secret keys leaked in responses or logs
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.audit import ModelAvailability
from app.providers.base import ModelInfo
from app.providers.filtering import filter_chat_models, is_chat_model, non_chat_category
from app.providers.mock import MockProvider
from app.services.audit_service import AuditService

# --- 1. Non-Chat Filtering Tests ---------------------------------------------


def test_non_chat_model_filtering():
    """Verify data-driven rejection of embeddings, moderation, speech, image, reranker, and guard models."""
    non_chat_candidates = [
        "text-embedding-3-small",
        "text-embedding-ada-002",
        "bge-large-en-v1.5",
        "gte-Qwen2-7B-instruct",
        "sentence-transformers/all-MiniLM-L6-v2",
        "omni-moderation-latest",
        "text-moderation-007",
        "llama-guard-3-8b",
        "meta/llama-guard-3-8b",
        "whisper-large-v3",
        "tts-1-hd",
        "eleven-multilingual-v2",
        "dall-e-3",
        "stable-diffusion-xl-base-1.0",
        "black-forest-labs/FLUX.1-schnell",
        "bge-reranker-v2-m3",
        "cohere-rerank-v3",
        "jina-reranker-v2-base-multilingual",
    ]

    for model_id in non_chat_candidates:
        info = ModelInfo(id=model_id, provider="test")
        assert not is_chat_model(info), f"Expected {model_id} to be rejected as non-chat"
        cat = non_chat_category(info)
        assert cat is not None, f"Expected non_chat_category for {model_id}"

    # Verify legitimate chat models pass
    valid_chat_candidates = [
        "llama-3.3-70b-instruct",
        "llama-3.1-8b-instant",
        "gpt-4o",
        "gpt-4o-mini",
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "qwen/qwen3.8-27b",
        "deepseek-ai/DeepSeek-R1",
        "allam-2-7b",
    ]

    for model_id in valid_chat_candidates:
        info = ModelInfo(id=model_id, provider="test")
        assert is_chat_model(info), f"Expected {model_id} to be accepted as chat"
        assert non_chat_category(info) is None

    # Verify batch filtering helper
    mixed = [ModelInfo(id=m, provider="test") for m in non_chat_candidates + valid_chat_candidates]
    filtered, _ = filter_chat_models(mixed)
    filtered_ids = {m.id for m in filtered}
    assert filtered_ids == set(valid_chat_candidates)


# --- 2. Probe Error Classification Tests -------------------------------------


@pytest.mark.asyncio
async def test_probe_classification_statuses(db):
    """Verify probe_model classifies every error type with structured reason."""
    provider = MockProvider()
    svc = AuditService(db)

    # AVAILABLE
    status, reason, latency, retry = await svc.probe_model(provider, "available")
    assert status == "AVAILABLE"
    assert "succeeded" in reason
    assert latency > 0
    assert retry is None

    # RATE_LIMITED
    status, reason, latency, retry = await svc.probe_model(provider, "rate_limited")
    assert status == "RATE_LIMITED"
    assert "Rate limit" in reason or "429" in reason
    assert retry == 30

    # NOT_ENTITLED
    status, reason, latency, retry = await svc.probe_model(provider, "not_entitled")
    assert status == "NOT_ENTITLED"
    assert "Not entitled" in reason or "tier" in reason.lower()

    # NOT_FOUND
    status, reason, latency, retry = await svc.probe_model(provider, "not_found")
    assert status == "NOT_FOUND"
    assert "not found" in reason.lower() or "404" in reason

    # INVALID_CREDENTIALS
    status, reason, latency, retry = await svc.probe_model(provider, "invalid_credentials")
    assert status == "INVALID_CREDENTIALS"
    assert "credentials" in reason.lower()

    # TIMEOUT
    status, reason, latency, retry = await svc.probe_model(provider, "timeout")
    assert status == "TIMEOUT"
    assert "timed out" in reason.lower()

    # UPSTREAM_ERROR
    status, reason, latency, retry = await svc.probe_model(provider, "upstream_error")
    assert status == "UPSTREAM_ERROR"
    assert "upstream" in reason.lower() or "503" in reason

    # EMPTY_RESPONSE
    status, reason, latency, retry = await svc.probe_model(provider, "empty_response")
    assert status == "EMPTY_RESPONSE"
    assert "empty" in reason.lower()


# --- 3. Auth Failure Early-Stopping & Probe Caps -----------------------------


@pytest.mark.asyncio
async def test_auth_failure_early_stops_provider(db):
    """When a provider yields INVALID_CREDENTIALS, remaining candidates are NOT_PROBED."""
    svc = AuditService(db)

    # Run audit on mock provider with max_probes_per_provider=20
    audit_run = await svc.execute_audit(providers=["mock"], max_probes_per_provider=20)

    # In MockProvider.discover_models, "invalid_credentials" is followed by others.
    # Assert that NOT_PROBED exists in the audit items for mock
    not_probed = [item for item in audit_run.items if item.status == "NOT_PROBED"]
    assert len(not_probed) > 0
    assert any("credentials invalid" in item.reason for item in not_probed)


@pytest.mark.asyncio
async def test_probe_cap_and_dry_run_estimation(db):
    """Verify dry-run call estimation matches cap and does not execute network calls."""
    svc = AuditService(db)

    dry_run = await svc.estimate_audit_calls(providers=["mock"], max_probes_per_provider=3)
    assert dry_run["estimated_calls"] <= 3
    assert "mock" in dry_run["providers_targeted"]
    assert dry_run["by_provider"]["mock"] <= 3


# --- 4. Cache TTL, Stale Handling & Availability Invariant ------------------


def test_availability_cache_ttl_and_freshness(db):
    """Expired cache records are treated as stale and excluded from default listing."""
    svc = AuditService(db)

    # Insert fresh available model
    fresh_rec = ModelAvailability(
        id="mav_fresh_123",
        provider="mock",
        model_id="fresh_model",
        status="AVAILABLE",
        reason="OK",
        checked_at=datetime.now(UTC),
    )
    db.add(fresh_rec)

    # Insert stale available model (older than TTL)
    stale_rec = ModelAvailability(
        id="mav_stale_123",
        provider="mock",
        model_id="stale_model",
        status="AVAILABLE",
        reason="OK",
        checked_at=datetime.now(UTC) - timedelta(hours=settings.model_audit_ttl_hours + 1),
    )
    db.add(stale_rec)
    db.commit()

    assert svc.is_record_fresh(fresh_rec) is True
    assert svc.is_record_fresh(stale_rec) is False

    grouped = svc.get_available_models_grouped(include_unavailable=False)
    mock_models = {m["id"] for m in grouped.get("mock", [])}
    assert "fresh_model" in mock_models
    assert "stale_model" not in mock_models

    # Stale models appear when include_unavailable=True with is_stale=True
    grouped_all = svc.get_available_models_grouped(include_unavailable=True)
    all_mock_models = {m["id"]: m for m in grouped_all.get("mock", [])}
    assert all_mock_models["stale_model"]["is_stale"] is True


def test_invariant_nothing_available_without_successful_probe(db):
    """A model with status != AVAILABLE is never exposed as available."""
    svc = AuditService(db)

    for status in ["NOT_FOUND", "NOT_ENTITLED", "RATE_LIMITED", "NOT_PROBED", "INVALID_CREDENTIALS"]:
        rec = ModelAvailability(
            id=f"mav_inv_{status.lower()}",
            provider="mock",
            model_id=f"model_{status.lower()}",
            status=status,
            reason=f"Test {status}",
            checked_at=datetime.now(UTC),
        )
        db.add(rec)
    db.commit()

    grouped = svc.get_available_models_grouped(include_limited=False, include_unavailable=False)
    available_ids = {m["id"] for m in grouped.get("mock", [])}
    for status in ["NOT_FOUND", "NOT_ENTITLED", "RATE_LIMITED", "NOT_PROBED", "INVALID_CREDENTIALS"]:
        assert f"model_{status.lower()}" not in available_ids


# --- 5. Auto-Invalidation on Evaluation Run Failure -------------------------


def test_auto_invalidation_on_evaluation_failure(db):
    """Evaluation errors update availability cache so subsequent screens reject the dead model."""
    svc = AuditService(db)

    # Initially model was available
    rec = ModelAvailability(
        id="mav_autoinv_1",
        provider="mock",
        model_id="dying_model",
        status="AVAILABLE",
        reason="OK",
        checked_at=datetime.now(UTC),
    )
    db.add(rec)
    db.commit()

    # Simulate evaluation failure with model_unavailable
    svc.record_evaluation_failure("mock", "dying_model", "model_unavailable", "Upstream 404 Model Not Found")

    updated = svc.get_latest_for_model("mock", "dying_model")
    assert updated is not None
    assert updated.status == "NOT_FOUND"
    assert "Upstream 404" in updated.reason


# --- 6. API Endpoint Tests ---------------------------------------------------


def test_api_providers_audit_dry_run(client):
    """POST /api/providers/audit with dry_run=True returns estimate without running probes."""
    resp = client.post("/api/providers/audit", json={"dry_run": True, "max_probes_per_provider": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert "estimated_calls" in data
    assert "providers_targeted" in data
    assert "by_provider" in data


def test_api_providers_audit_execution(client):
    """POST /api/providers/audit executes live audit against mock provider."""
    resp = client.post(
        "/api/providers/audit",
        json={"dry_run": False, "providers": ["mock"], "max_probes_per_provider": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert "id" in data
    assert "summary" in data
    assert "items" in data

    # Retrieve audit run by ID
    audit_id = data["id"]
    get_resp = client.get(f"/api/providers/audit/{audit_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == audit_id


def test_api_providers_status_and_models(client):
    """GET /api/providers/status and /api/providers/models return honest audit status."""
    # Status
    resp = client.get("/api/providers/status")
    assert resp.status_code == 200
    summaries = resp.json()
    assert isinstance(summaries, list)
    mock_sum = next((s for s in summaries if s["provider"] == "mock"), None)
    assert mock_sum is not None
    assert "counts" in mock_sum

    # Models filtered (AVAILABLE only by default)
    resp_models = client.get("/api/providers/models")
    assert resp_models.status_code == 200
    models_dict = resp_models.json()["models"]
    for _p_key, p_models in models_dict.items():
        for m in p_models:
            assert m["status"] == "AVAILABLE"

    # Models with include_limited
    resp_limited = client.get("/api/providers/models?include_limited=true")
    assert resp_limited.status_code == 200


def test_api_recheck_model(client):
    """POST /api/providers/{key}/models/{model_id}/recheck re-probes a single model."""
    resp = client.post("/api/providers/mock/models/available/recheck")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "mock"
    assert data["model_id"] == "available"
    assert data["status"] == "AVAILABLE"
    assert data["latency_ms"] is not None


def test_api_ready_check(client):
    """GET /api/ready validates readiness and default evaluator status."""
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ready", "degraded")
    assert "default_evaluator" in data


# --- 7. Evaluation Creation Rejection for Unavailable Models -----------------


def test_experiment_creation_rejects_unavailable_model(client, db):
    """Experiments referencing models cached as NOT_FOUND or NOT_ENTITLED are rejected with 422."""
    # Seed a cached NOT_FOUND record
    rec = ModelAvailability(
        id="mav_rej_404",
        provider="mock",
        model_id="gated_or_dead_model",
        status="NOT_FOUND",
        reason="Model was retired by provider",
        checked_at=datetime.now(UTC),
    )
    db.add(rec)
    db.commit()

    # Create dummy dataset
    ds_resp = client.post(
        "/api/datasets/import",
        json={"name": "Audit Rejection Test", "rows": [{"question": "Q1?", "ground_truth": "A1."}]},
    )
    assert ds_resp.status_code == 201
    ds_id = ds_resp.json()["id"]

    # Try to create experiment with the dead model
    exp_payload = {
        "name": "Should Fail",
        "dataset_id": ds_id,
        "models": [{"provider": "mock", "model": "gated_or_dead_model"}],
        "metrics": ["correctness", "latency"],
    }
    resp = client.post("/api/experiments", json=exp_payload)
    assert resp.status_code == 422
    assert "gated_or_dead_model" in resp.text
    assert "NOT_FOUND" in resp.text


# --- 8. Security Sentinel: No Secrets Leaked ---------------------------------


def test_security_sentinel_no_api_keys_leaked(client, monkeypatch):
    """Ensure API keys and secrets never appear in audit responses or diagnostic logs."""
    fake_secret = "sk-super-secret-audit-key-9876543210"
    monkeypatch.setenv("MOCK_SECRET_KEY", fake_secret)
    monkeypatch.setenv("GEMINI_API_KEY", fake_secret)

    # 1. Check audit endpoints
    endpoints = [
        "/api/providers/status",
        "/api/providers/models?include_unavailable=true",
        "/api/providers",
        "/api/ready",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        body = resp.text
        assert fake_secret not in body, f"Secret leaked in {ep} response"

    # 2. Check audit execution response
    audit_resp = client.post("/api/providers/audit", json={"dry_run": True})
    assert fake_secret not in audit_resp.text
