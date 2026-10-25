"""Pytest fixtures.

The whole suite runs offline against the deterministic test provider, so it
never depends on a paid API and produces identical results on every run.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP_DIR = Path(tempfile.mkdtemp(prefix="evalhub-tests-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TMP_DIR / 'test.db'}")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ENABLE_MOCK_PROVIDER", "true")
os.environ.setdefault("STORAGE_DIR", str(TMP_DIR / "storage"))
os.environ.setdefault("MAX_CONCURRENT_REQUESTS", "4")
for _key in (
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "HF_API_KEY",
    "OPENROUTER_API_KEY",
    "NVIDIA_NIM_API_KEY",
):
    os.environ[_key] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sample_rows() -> list[dict]:
    return [
        {
            "id": "tc-1",
            "question": "What is the refund window?",
            "ground_truth": "Customers can request a refund within 30 days.",
            "context": "Refunds are available within 30 days of purchase.",
            "category": "policy",
            "difficulty": "easy",
            "tags": "refund,policy",
        },
        {
            "id": "tc-2",
            "question": "How long is the warranty?",
            "ground_truth": "The warranty lasts 24 months.",
            "context": "All electronics carry a 24 month warranty against defects.",
            "category": "policy",
            "difficulty": "medium",
        },
        {
            "id": "tc-3",
            "question": "Can I return opened items?",
            "ground_truth": "Opened items receive store credit only.",
            "context": "Opened items are eligible for store credit only, within 14 days.",
            "category": "policy",
            "difficulty": "medium",
        },
    ]


def wait_for_run(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
    """Poll a run to completion. The deterministic provider makes this fast."""
    import time

    deadline = time.time() + timeout
    payload: dict = {}
    while time.time() < deadline:
        payload = client.get(f"/api/evaluations/{run_id}").json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish within {timeout}s")
