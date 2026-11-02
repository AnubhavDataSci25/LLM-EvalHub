"""Cross-checks documented environment variables and API endpoints against reality.

Ensures that:
1. Every environment variable documented in installation.js exists in .env.example and Settings.
2. Core documented API routes exist in the backend FastAPI application and OpenAPI schema.
3. Group A documentation content files are present, well-formed, and non-empty.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = ROOT_DIR / ".env.example"
DOCS_INSTALLATION = ROOT_DIR / "frontend" / "src" / "content" / "docs" / "sections" / "installation.js"
DOCS_DIR = ROOT_DIR / "frontend" / "src" / "content" / "docs" / "sections"


def test_documented_env_vars_exist_in_example_and_settings() -> None:
    """Verifies that every variable documented in the docs table matches .env.example."""
    assert ENV_EXAMPLE.exists(), f"Missing .env.example at {ENV_EXAMPLE}"
    assert DOCS_INSTALLATION.exists(), f"Missing installation doc at {DOCS_INSTALLATION}"

    # Extract all env var names from .env.example
    env_lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    example_vars = set()
    for line in env_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            var_name = line.split("=", 1)[0].strip()
            example_vars.add(var_name)

    # Extract all documented variable names from installation.js rows
    doc_content = DOCS_INSTALLATION.read_text(encoding="utf-8")
    matches = re.findall(r"\['`([A-Z0-9_]+)`',", doc_content)
    assert len(matches) > 10, f"Failed to extract documented variables from {DOCS_INSTALLATION}"

    documented_vars = set(matches)

    # Every documented variable must be in .env.example or in backend Settings
    settings_fields = {k.upper() for k in settings.model_fields.keys()}
    all_valid_vars = example_vars | settings_fields

    for var in documented_vars:
        assert (
            var in all_valid_vars
        ), f"Documented variable '{var}' does not exist in .env.example or backend Settings!"


def test_core_documented_api_endpoints_exist_in_openapi() -> None:
    """Verifies that documented API endpoints exist in FastAPI routes and OpenAPI schema."""
    with TestClient(app) as client:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200, "Failed to retrieve /openapi.json"
        openapi = resp.json()
        paths = openapi.get("paths", {})

        # List of critical documented routes
        core_endpoints = [
            "/api/health",
            "/api/ready",
            "/api/benchmarks",
            "/api/datasets",
            "/api/evaluations",
            "/api/evaluations/run",
            "/api/compare",
            "/api/failures",
            "/api/recommendations",
            "/api/reports",
            "/api/documents",
        ]

        for endpoint in core_endpoints:
            assert endpoint in paths, f"Documented API endpoint '{endpoint}' not found in OpenAPI schema!"


def test_group_a_b_c_d_sections_exist_and_non_empty() -> None:
    """Verifies all Group A, B, C, and D section files exist and contain non-empty content."""
    required_sections = [
        # Group A
        "overview.js",
        "quickstart.js",
        "installation.js",
        "concepts.js",
        # Group B
        "dashboard.js",
        "datasets.js",
        "benchmarks.js",
        "documents.js",
        "newEvaluation.js",
        "runningEvaluations.js",
        "experiments.js",
        "compare.js",
        "failuresDiagnosis.js",
        "improvementLoop.js",
        "recommendations.js",
        "reports.js",
        "settingsProviders.js",
        # Group C
        "metricsReference.js",
        "scoreLimitations.js",
        # Group D
        "architecture.js",
        "apiReference.js",
        "addingProvider.js",
        "addingMetricPack.js",
        "dataModel.js",
    ]
    for filename in required_sections:
        file_path = DOCS_DIR / filename
        assert file_path.exists(), f"Documentation file missing: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert len(content) > 200, f"Documentation file {filename} is suspiciously short"
        assert "id:" in content, f"Documentation file {filename} missing id field"
        assert "title:" in content, f"Documentation file {filename} missing title field"
        assert "blocks:" in content, f"Documentation file {filename} missing blocks field"
