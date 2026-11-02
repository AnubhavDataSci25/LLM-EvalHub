"""Tests for Security and Operations (Part 4).

Covers:
- Security headers middleware
- Request ID tracing and propagation
- Payload size limit rejection (413)
- Sensitive secret, token, and password redaction in logging
- /health and /ready readiness probes
- Workspace audit log recording and owner-only retrieval
- Prometheus-compatible /metrics endpoint
"""

from __future__ import annotations

import logging
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.logging import RedactingFilter, redact_secrets
from app.core.metrics import metrics_collector
from app.main import app
from app.services.auth_service import AuthService
from app.services.workspace_service import WorkspaceService


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_security_headers_present(client: TestClient) -> None:
    """Every HTTP response must contain the hardened security headers."""
    resp = client.get("/api/meta/metrics")
    assert resp.status_code == 200

    headers = resp.headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-XSS-Protection"] == "1; mode=block"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in headers["Permissions-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "X-Request-ID" in headers
    assert headers["X-Request-ID"].startswith("req_")


def test_request_id_propagation(client: TestClient) -> None:
    """Incoming X-Request-ID must be preserved in context and echoed in response headers."""
    custom_id = "trace-custom-uuid-9999"
    resp = client.get("/api/meta/metrics", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == custom_id


def test_payload_too_large_rejection(client: TestClient) -> None:
    """Requests exceeding max_upload_bytes must be rejected immediately with 413."""
    oversized = settings.max_upload_bytes + 1024
    resp = client.post(
        "/api/datasets/upload",
        headers={"Content-Length": str(oversized)},
        content=b"test",
    )
    assert resp.status_code == 413
    payload = resp.json()
    assert payload["error"]["code"] == "payload_too_large"


def test_redaction_scrubs_keys_tokens_and_passwords() -> None:
    """Secrets, Bearer tokens, and password fields must be masked by the redacting filter."""
    # 1. API Keys
    sample_key = "Groq key is gsk_1234567890abcdef and OpenAI is sk-abcdef1234567890"
    redacted_key = redact_secrets(sample_key)
    assert "gsk_" not in redacted_key
    assert "sk-" not in redacted_key
    assert "***redacted***" in redacted_key

    # 2. Bearer tokens
    sample_token = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
    redacted_token = redact_secrets(sample_token)
    assert "eyJhbG" not in redacted_token
    assert "Bearer [REDACTED]" in redacted_token

    # 3. Passwords in JSON/strings
    sample_json = '{"email": "test@eval.local", "password": "supersecretpassword123"}'
    redacted_json = redact_secrets(sample_json)
    assert "supersecretpassword123" not in redacted_json
    assert '"password": "[REDACTED]"' in redacted_json

    # 4. Filter behavior on LogRecord
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Login with password '%s' and key %s",
        args=("secretpass", "sk-12345678901234"),
        exc_info=None,
    )
    redactor = RedactingFilter()
    redactor.filter(record)
    formatted = record.msg % record.args
    assert "secretpass" not in formatted
    assert "sk-123" not in formatted


def test_health_and_readiness_checks(client: TestClient) -> None:
    """Both root and /api/ health and readiness probes must report system status."""
    # Root /health and /api/health
    resp_root = client.get("/health")
    resp_api = client.get("/api/health")
    assert resp_root.status_code == 200
    assert resp_api.status_code == 200
    assert resp_root.json()["status"] == "ok"
    assert resp_api.json()["database"] in {"sqlite", "postgresql"}

    # Root /ready and /api/ready
    resp_ready_root = client.get("/ready")
    resp_ready_api = client.get("/api/ready")
    assert resp_ready_root.status_code == 200
    assert resp_ready_api.status_code == 200
    ready_data = resp_ready_api.json()
    assert ready_data["status"] in {"ready", "degraded"}
    assert ready_data["database"]["status"] == "connected"
    assert "redis" in ready_data


def test_audit_logs_owner_access_and_actions(client: TestClient, db) -> None:
    """Sensitive actions create audit log records accessible only by workspace owners."""
    auth_svc = AuthService(db)
    wks_svc = WorkspaceService(db)

    # 1. Register owner user and create workspace
    owner, owner_tokens = auth_svc.register(
        email="owner_audit@test.local",
        password="SecurePassword123!",
        full_name="Audit Owner",
        workspace_name="Audit Security Wks",
    )
    workspaces = wks_svc.list_user_workspaces(owner)
    wks_id = workspaces[0].id

    # 2. Register viewer user
    viewer, viewer_tokens = auth_svc.register(
        email="viewer_audit@test.local",
        password="SecurePassword123!",
        full_name="Audit Viewer",
    )
    # Add viewer to workspace
    from app.schemas.auth import WorkspaceMemberInviteRequest
    wks_svc.add_or_invite_member(
        wks_id,
        WorkspaceMemberInviteRequest(email=viewer.email, role="viewer"),
    )

    # 3. Add encrypted provider key as owner (creates audit log)
    client.put(
        f"/api/workspaces/{wks_id}/providers/groq",
        headers={"Authorization": f"Bearer {owner_tokens.access_token}"},
        json={"api_key": "gsk_live_audit_test_key_1234"},
    )

    # 4. Query audit logs as owner (must succeed)
    owner_resp = client.get(
        f"/api/workspaces/{wks_id}/audit-logs",
        headers={"Authorization": f"Bearer {owner_tokens.access_token}"},
    )
    assert owner_resp.status_code == 200
    logs_data = owner_resp.json()
    assert logs_data["total"] >= 1
    actions = [item["action"] for item in logs_data["items"]]
    assert "provider_key.update" in actions

    # 5. Query audit logs as viewer (must be rejected with 403 Forbidden)
    viewer_resp = client.get(
        f"/api/workspaces/{wks_id}/audit-logs",
        headers={"Authorization": f"Bearer {viewer_tokens.access_token}"},
    )
    assert viewer_resp.status_code == 403


def test_prometheus_metrics_exposition(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prometheus /metrics endpoint is controlled by ENABLE_METRICS and outputs standard exposition."""
    # When disabled (default)
    monkeypatch.setattr(settings, "enable_metrics", False)
    resp_disabled = client.get("/metrics")
    assert resp_disabled.status_code == 404

    # When enabled
    monkeypatch.setattr(settings, "enable_metrics", True)
    metrics_collector.record_job("queued")
    metrics_collector.record_provider_error("groq", "rate_limited")

    resp_enabled = client.get("/metrics")
    assert resp_enabled.status_code == 200
    assert "text/plain" in resp_enabled.headers["content-type"]
    text = resp_enabled.text

    assert "evalhub_http_requests_total" in text
    assert "evalhub_jobs_total{status=\"queued\"}" in text
    assert "evalhub_provider_errors_total{provider=\"groq\",error_type=\"rate_limited\"}" in text
