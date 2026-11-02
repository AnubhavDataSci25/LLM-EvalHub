"""Tests for durable background job execution, cancellation, restart recovery, and limits."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import new_id
from app.models.experiment import EvaluationResult, EvaluationRun, Experiment
from app.models.job import Job
from app.schemas.experiment import RunEvaluationRequest
from app.services.evaluation_service import EvaluationService
from app.services.jobs import (
    ArqJobBackend,
    AsyncioJobBackend,
    JobService,
    get_job_backend,
    reset_job_backend_for_tests,
)
from tests.conftest import wait_for_run


def _create_test_experiment(client: TestClient, sample_rows: list[dict]) -> str:
    # 1. Create dataset via import
    ds_resp = client.post(
        "/api/datasets/import",
        json={"name": "Job Test Dataset", "domain": "policy", "rows": sample_rows},
    )
    assert ds_resp.status_code == 201, ds_resp.text
    dataset_id = ds_resp.json()["id"]

    # 2. Create experiment
    exp_resp = client.post(
        "/api/experiments",
        json={
            "name": "Job Test Experiment",
            "dataset_id": dataset_id,
            "models": [{"provider": "mock", "model": "mock-extractive"}],
            "metrics": ["correctness"],
        },
    )
    assert exp_resp.status_code == 201, exp_resp.text
    return exp_resp.json()["id"]


def test_job_lifecycle_and_persistence(client: TestClient, db: Session, sample_rows: list[dict]):
    """Submitting a run creates a persistent Job row that transitions to succeeded upon completion."""
    exp_id = _create_test_experiment(client, sample_rows[:2])

    resp = client.post("/api/evaluations/run", json={"experiment_id": exp_id})
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    # Poll run to completion
    payload = wait_for_run(client, run_id)
    assert payload["status"] == "completed"

    # Refresh job from DB
    db.expire_all()
    job = db.get(Job, f"job_{run_id}")
    assert job is not None
    assert job.status == "succeeded"
    assert job.completed_units == 2
    assert job.progress == 1.0
    assert job.completed_at is not None

    # Test /api/jobs listing endpoint
    jobs_resp = client.get("/api/jobs")
    assert jobs_resp.status_code == 200
    jobs_data = jobs_resp.json()
    assert any(j["id"] == f"job_{run_id}" for j in jobs_data["items"])

    # Test /api/jobs/{id} endpoint
    single_job_resp = client.get(f"/api/jobs/job_{run_id}")
    assert single_job_resp.status_code == 200
    assert single_job_resp.json()["id"] == f"job_{run_id}"


def test_job_cancellation(client: TestClient, db: Session, sample_rows: list[dict]):
    """Cancelling a queued run updates status to cancelled and registers cancellation."""
    exp_id = _create_test_experiment(client, sample_rows)
    exp = db.get(Experiment, exp_id)

    # Create run without triggering background runner immediately
    service = EvaluationService(db)
    run = service.create_run(RunEvaluationRequest(experiment_id=exp.id), workspace_id=exp.workspace_id)
    db.commit()

    # Cancel via endpoint
    cancel_resp = client.post(f"/api/evaluations/{run.id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Check job is cancelled in DB
    db.expire_all()
    job = db.get(Job, f"job_{run.id}")
    assert job is not None
    assert job.status == "cancelled"

    # Check cancellation flag is registered in backend
    assert get_job_backend().is_cancelled(f"job_{run.id}") is True

    # Check cancellation is idempotent
    cancel_again = client.post(f"/api/evaluations/{run.id}/cancel")
    assert cancel_again.status_code == 200
    assert cancel_again.json()["status"] == "cancelled"


def test_restart_safety_and_orphan_recovery(client: TestClient, db: Session, sample_rows: list[dict]):
    """Orphaned running or queued jobs and runs are marked as interrupted upon server restart."""
    exp_id = _create_test_experiment(client, sample_rows[:1])
    exp = db.get(Experiment, exp_id)

    # Insert an orphaned run and job simulating a sudden server crash
    orphan_run_id = new_id("run")
    orphan_run = EvaluationRun(
        id=orphan_run_id,
        workspace_id=exp.workspace_id,
        experiment_id=exp.id,
        status="running",
        stage="evaluating",
        total_units=1,
        completed_units=0,
    )
    db.add(orphan_run)

    orphan_job = Job(
        id=f"job_{orphan_run_id}",
        workspace_id=exp.workspace_id,
        job_type="evaluation_run",
        entity_id=orphan_run_id,
        status="running",
        total_units=1,
        completed_units=0,
    )
    db.add(orphan_job)
    db.commit()

    # Simulate startup recovery
    recovered_count = JobService.recover_interrupted_jobs()
    assert recovered_count >= 1

    db.expire_all()
    recovered_job = db.get(Job, f"job_{orphan_run_id}")
    assert recovered_job.status == "interrupted"
    assert "interrupted" in recovered_job.last_error.lower()

    recovered_run = db.get(EvaluationRun, orphan_run_id)
    assert recovered_run.status == "interrupted"
    assert "interrupted" in recovered_run.error.lower()


def test_resume_skips_already_completed_units(client: TestClient, db: Session, sample_rows: list[dict]):
    """Resuming an interrupted run does not re-run already completed work units (idempotent persistence)."""
    exp_id = _create_test_experiment(client, sample_rows[:2])
    exp = db.get(Experiment, exp_id)
    eval_service = EvaluationService(db)
    cases = eval_service.datasets.test_cases(exp.dataset_version_id)
    assert len(cases) == 2
    case_0_id = cases[0].id
    case_1_id = cases[1].id

    # Create run in interrupted state
    run_id = new_id("run")
    run = EvaluationRun(
        id=run_id,
        workspace_id=exp.workspace_id,
        experiment_id=exp.id,
        status="interrupted",
        total_units=2,
        completed_units=1,
        config_snapshot={"case_ids": [case_0_id, case_1_id]},
    )
    db.add(run)

    job = Job(
        id=f"job_{run_id}",
        workspace_id=exp.workspace_id,
        job_type="evaluation_run",
        entity_id=run_id,
        status="interrupted",
        total_units=2,
        completed_units=1,
        payload={"run_id": run_id},
    )
    db.add(job)

    # Pre-insert a completed result for case 0
    pre_result = EvaluationResult(
        id=new_id("res"),
        run_id=run_id,
        experiment_id=exp.id,
        test_case_id=case_0_id,
        provider="mock",
        model="mock-extractive",
        status="completed",
        passed=True,
        latency_ms=10.0,
        composite_score=0.95,
    )
    db.add(pre_result)
    db.commit()

    # Resume the run via endpoint
    resume_resp = client.post(f"/api/evaluations/{run_id}/resume")
    assert resume_resp.status_code == 202
    assert resume_resp.json()["status"] == "queued"

    # Wait for completion
    finished_run = wait_for_run(client, run_id)
    assert finished_run["status"] == "completed"

    # Check results in DB
    db.expire_all()
    results = db.execute(
        select(EvaluationResult).where(EvaluationResult.run_id == run_id)
    ).scalars().all()

    # Total results must be exactly 2 (the pre-existing one + the newly run one, no duplicates)
    assert len(results) == 2
    found_case_ids = {r.test_case_id for r in results}
    assert found_case_ids == {case_0_id, case_1_id}

    # Pre-existing result ID was preserved, not duplicated
    assert any(r.id == pre_result.id for r in results)


def test_workspace_concurrency_limit(client: TestClient, db: Session, sample_rows: list[dict]):
    """Reaching the workspace concurrent job limit rejects new runs with HTTP 429."""
    exp_id = _create_test_experiment(client, sample_rows[:1])
    exp = db.get(Experiment, exp_id)

    # Set concurrency limit to 1
    with patch.object(settings, "workspace_max_concurrent_jobs", 1):
        # Insert a running job
        running_job = Job(
            id=new_id("job"),
            workspace_id=exp.workspace_id,
            job_type="evaluation_run",
            status="running",
            total_units=1,
        )
        db.add(running_job)
        db.commit()

        # Attempt to create another run
        resp = client.post("/api/evaluations/run", json={"experiment_id": exp_id})
        assert resp.status_code == 429
        assert "concurrent job limit reached" in resp.json()["error"]["message"]


def test_workspace_daily_call_limit(client: TestClient, db: Session, sample_rows: list[dict]):
    """Exceeding the workspace daily call quota rejects new runs with HTTP 429."""
    exp_id = _create_test_experiment(client, sample_rows[:2])
    exp = db.get(Experiment, exp_id)
    eval_service = EvaluationService(db)
    cases = eval_service.datasets.test_cases(exp.dataset_version_id)
    valid_case_id = cases[0].id

    with patch.object(settings, "workspace_daily_call_limit", 5):
        # Insert 5 completed evaluation results today
        mock_run = EvaluationRun(
            id=new_id("run"),
            workspace_id=exp.workspace_id,
            experiment_id=exp.id,
            status="completed",
            total_units=5,
            completed_units=5,
        )
        db.add(mock_run)

        for _ in range(5):
            res = EvaluationResult(
                id=new_id("res"),
                run_id=mock_run.id,
                experiment_id=exp.id,
                test_case_id=valid_case_id,
                provider="mock",
                model="mock-extractive",
                status="completed",
                created_at=datetime.now(UTC),
            )
            db.add(res)
        db.commit()

        # Attempt to run an evaluation that requires 2 units (5 + 2 > 5)
        resp = client.post("/api/evaluations/run", json={"experiment_id": exp_id})
        assert resp.status_code == 429
        assert "daily LLM call limit reached" in resp.json()["error"]["message"]


def test_job_backend_selection():
    """get_job_backend selects AsyncioJobBackend or ArqJobBackend based on settings."""
    reset_job_backend_for_tests()
    with patch.object(settings, "redis_url", None), patch.object(settings, "job_backend", "auto"):
        backend = get_job_backend()
        assert isinstance(backend, AsyncioJobBackend)

    reset_job_backend_for_tests()
    with patch.object(settings, "redis_url", "redis://localhost:6379/0"), patch.object(settings, "job_backend", "arq"):
        backend = get_job_backend()
        assert isinstance(backend, ArqJobBackend)
    reset_job_backend_for_tests()
