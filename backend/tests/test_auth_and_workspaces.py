"""Tests for Part 1: Authentication, Workspaces, RBAC, and Encrypted Provider Keys."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.security import auth_limiter, decrypt_secret
from app.models.auth import WorkspaceProviderKey


def test_auth_mode_endpoint(client: TestClient):
    res = client.get("/api/auth/mode")
    assert res.status_code == 200
    data = res.json()
    assert "mode" in data
    assert "is_auth_enabled" in data


def test_user_registration_and_validation(client: TestClient):
    auth_limiter.reset()

    # Valid registration
    res = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "password": "StrongPassword123!",
            "full_name": "Alice Tester",
        },
    )
    assert res.status_code == 201
    user = res.json()
    assert user["email"] == "alice@example.com"
    assert user["full_name"] == "Alice Tester"
    assert "password" not in user
    assert "hashed_password" not in user

    # Duplicate registration rejected
    dup = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "password": "AnotherPassword123!",
        },
    )
    assert dup.status_code == 409

    # Password too short rejected
    short = client.post(
        "/api/auth/register",
        json={
            "email": "bob@example.com",
            "password": "short",
        },
    )
    assert short.status_code == 422


def test_login_and_token_flow(client: TestClient):
    auth_limiter.reset()

    client.post(
        "/api/auth/register",
        json={"email": "loginuser@example.com", "password": "Password123!"},
    )

    # Invalid password -> 401 without leaking user existence
    bad_login = client.post(
        "/api/auth/login",
        json={"email": "loginuser@example.com", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    # Nonexistent user -> 401 same message
    no_user = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "WrongPassword!"},
    )
    assert no_user.status_code == 401

    # Valid login
    login_res = client.post(
        "/api/auth/login",
        json={"email": "loginuser@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    # Profile check with access token
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    profile = me_res.json()
    assert profile["user"]["email"] == "loginuser@example.com"
    assert len(profile["workspaces"]) >= 1  # Personal workspace created on register


def test_token_rotation_and_revocation(client: TestClient):
    auth_limiter.reset()

    reg = client.post(
        "/api/auth/register",
        json={"email": "rotate@example.com", "password": "Password123!"},
    )
    assert reg.status_code == 201

    login_res = client.post(
        "/api/auth/login",
        json={"email": "rotate@example.com", "password": "Password123!"},
    )
    tokens = login_res.json()
    r1 = tokens["refresh_token"]

    # Rotate refresh token
    ref_res = client.post("/api/auth/refresh", json={"refresh_token": r1})
    assert ref_res.status_code == 200
    rotated_tokens = ref_res.json()
    r2 = rotated_tokens["refresh_token"]
    assert r2 != r1

    # Re-using old refresh token r1 must fail (token replay detection)
    replay_res = client.post("/api/auth/refresh", json={"refresh_token": r1})
    assert replay_res.status_code == 401

    # Logout with r2
    logout_res = client.post("/api/auth/logout", json={"refresh_token": r2})
    assert logout_res.status_code == 200

    # Using r2 after logout fails
    after_logout = client.post("/api/auth/refresh", json={"refresh_token": r2})
    assert after_logout.status_code == 401


def test_workspace_isolation_prevents_leakage(client: TestClient):
    """User 2 must receive 404 (never 403) when attempting to access User 1's dataset."""
    auth_limiter.reset()

    # User 1
    client.post("/api/auth/register", json={"email": "tenant1@example.com", "password": "Password123!"})
    tok1 = client.post("/api/auth/login", json={"email": "tenant1@example.com", "password": "Password123!"}).json()
    h1 = {"Authorization": f"Bearer {tok1['access_token']}"}
    wks1 = client.get("/api/workspaces", headers=h1).json()[0]["id"]
    h1["X-Workspace-Id"] = wks1

    # Create dataset in workspace 1
    ds_res = client.post(
        "/api/datasets/import",
        headers=h1,
        json={
            "name": "Secret Tenant 1 Dataset",
            "rows": [{"question": "Q1?", "ground_truth": "A1."}],
        },
    )
    assert ds_res.status_code == 201
    ds1_id = ds_res.json()["id"]

    # User 2
    client.post("/api/auth/register", json={"email": "tenant2@example.com", "password": "Password123!"})
    tok2 = client.post("/api/auth/login", json={"email": "tenant2@example.com", "password": "Password123!"}).json()
    h2 = {"Authorization": f"Bearer {tok2['access_token']}"}
    wks2 = client.get("/api/workspaces", headers=h2).json()[0]["id"]
    h2["X-Workspace-Id"] = wks2

    # User 2 lists datasets: does NOT see User 1's dataset
    u2_list = client.get("/api/datasets", headers=h2).json()
    assert not any(d["id"] == ds1_id for d in u2_list["items"])

    # User 2 attempts to fetch User 1's dataset by ID -> MUST return 404, NOT 403
    u2_get = client.get(f"/api/datasets/{ds1_id}", headers=h2)
    assert u2_get.status_code == 404

    # User 2 attempts to update User 1's dataset -> MUST return 404
    u2_put = client.put(f"/api/datasets/{ds1_id}", headers=h2, json={"name": "Tampered"})
    assert u2_put.status_code == 404

    # User 2 attempts to delete User 1's dataset -> MUST return 404
    u2_del = client.delete(f"/api/datasets/{ds1_id}", headers=h2)
    assert u2_del.status_code == 404


def test_rbac_roles_hierarchy(client: TestClient):
    """Test Owner, Editor, Viewer permission enforcement."""
    auth_limiter.reset()

    # Owner creates workspace
    client.post("/api/auth/register", json={"email": "owner@example.com", "password": "Password123!"})
    tok_owner = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "Password123!"}).json()
    h_owner = {"Authorization": f"Bearer {tok_owner['access_token']}"}
    wks_id = client.get("/api/workspaces", headers=h_owner).json()[0]["id"]
    h_owner["X-Workspace-Id"] = wks_id

    # Create viewer and editor users
    client.post("/api/auth/register", json={"email": "viewer@example.com", "password": "Password123!"})
    tok_viewer = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "Password123!"}).json()
    h_viewer = {"Authorization": f"Bearer {tok_viewer['access_token']}", "X-Workspace-Id": wks_id}

    client.post("/api/auth/register", json={"email": "editor@example.com", "password": "Password123!"})
    tok_editor = client.post("/api/auth/login", json={"email": "editor@example.com", "password": "Password123!"}).json()
    h_editor = {"Authorization": f"Bearer {tok_editor['access_token']}", "X-Workspace-Id": wks_id}

    # Invite viewer and editor into workspace
    client.post(f"/api/workspaces/{wks_id}/members", headers=h_owner, json={"email": "viewer@example.com", "role": "viewer"})
    client.post(f"/api/workspaces/{wks_id}/members", headers=h_owner, json={"email": "editor@example.com", "role": "editor"})

    # 1. Viewer can read datasets
    view_list = client.get("/api/datasets", headers=h_viewer)
    assert view_list.status_code == 200

    # 2. Viewer CANNOT create datasets (requires editor) -> 403
    view_create = client.post(
        "/api/datasets/import",
        headers=h_viewer,
        json={"name": "VDS", "rows": [{"question": "Q?", "ground_truth": "A."}]},
    )
    assert view_create.status_code == 403

    # 3. Viewer CANNOT manage members -> 403
    view_member = client.post(
        f"/api/workspaces/{wks_id}/members",
        headers=h_viewer,
        json={"email": "someone@example.com", "role": "viewer"},
    )
    assert view_member.status_code == 403

    # 4. Editor CAN create datasets
    ed_create = client.post(
        "/api/datasets/import",
        headers=h_editor,
        json={"name": "EDS", "rows": [{"question": "Q?", "ground_truth": "A."}]},
    )
    assert ed_create.status_code == 201

    # 5. Editor CANNOT manage members (requires owner) -> 403
    ed_member = client.post(
        f"/api/workspaces/{wks_id}/members",
        headers=h_editor,
        json={"email": "someone@example.com", "role": "viewer"},
    )
    assert ed_member.status_code == 403

    # 6. Editor CANNOT manage provider keys (requires owner) -> 403
    ed_keys = client.put(
        f"/api/workspaces/{wks_id}/providers/groq",
        headers=h_editor,
        json={"api_key": "gsk_test123"},
    )
    assert ed_keys.status_code == 403

    # 7. Owner CAN manage provider keys
    owner_keys = client.put(
        f"/api/workspaces/{wks_id}/providers/groq",
        headers=h_owner,
        json={"api_key": "gsk_test123456789"},
    )
    assert owner_keys.status_code == 200


def test_encrypted_workspace_provider_keys(client: TestClient, db):
    """Verify keys are encrypted at rest, never returned plaintext, and decryptable."""
    auth_limiter.reset()

    client.post("/api/auth/register", json={"email": "secowner@example.com", "password": "Password123!"})
    tok = client.post("/api/auth/login", json={"email": "secowner@example.com", "password": "Password123!"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    wks_id = client.get("/api/workspaces", headers=h).json()[0]["id"]
    h["X-Workspace-Id"] = wks_id

    raw_secret = "gsk_super_secret_api_key_value_99"

    # Set key
    set_res = client.put(
        f"/api/workspaces/{wks_id}/providers/groq",
        headers=h,
        json={"api_key": raw_secret},
    )
    assert set_res.status_code == 200
    data = set_res.json()
    assert data["provider"] == "groq"
    assert data["is_configured"] is True
    assert data["has_workspace_key"] is True
    assert data["masked_suffix"].endswith("e_99")
    assert raw_secret not in str(data)  # Plaintext never returned

    # Check direct database record: MUST be encrypted ciphertext
    from sqlalchemy import select
    record = db.scalar(
        select(WorkspaceProviderKey).where(
            WorkspaceProviderKey.workspace_id == wks_id,
            WorkspaceProviderKey.provider == "groq",
        )
    )
    assert record is not None
    assert record.encrypted_key != raw_secret
    assert not record.encrypted_key.startswith("gsk_")
    # Verify Fernet decryption recovers the secret
    decrypted = decrypt_secret(record.encrypted_key)
    assert decrypted == raw_secret

    # Delete key
    del_res = client.delete(f"/api/workspaces/{wks_id}/providers/groq", headers=h)
    assert del_res.status_code == 204
