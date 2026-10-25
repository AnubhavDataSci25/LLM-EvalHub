#!/usr/bin/env python3
"""Seed a demo workspace so the UI has something real to show.

Installs a benchmark pack, runs an evaluation against the deterministic test
provider, diagnoses the failures, creates a follow-up experiment and generates a
report — the entire product loop, offline and reproducible.

    python scripts/seed.py [--pack rag_qa]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def wait(client: TestClient, run_id: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/evaluations/{run_id}").json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        print(f"   … {payload['completed_units']}/{payload['total_units']} units", end="\r")
        time.sleep(1)
    raise SystemExit(f"run {run_id} did not finish in {timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", default="rag_qa", help="benchmark pack key")
    args = parser.parse_args()

    with TestClient(app) as client:
        print(f"1/6  Installing benchmark pack '{args.pack}'…")
        installed = client.post(f"/api/benchmarks/{args.pack}/install", json={}).json()
        dataset, collection = installed["dataset"], installed.get("collection")
        print(f"     dataset {dataset['id']} with {dataset['row_count']} cases")

        print("2/6  Running a baseline evaluation…")
        experiment = {
            "name": f"{dataset['name']} — baseline",
            "dataset_id": dataset["id"],
            "models": [
                {"provider": "mock", "model": "mock-extractive"},
                {"provider": "mock", "model": "mock-hallucinate"},
            ],
            "metrics": [
                "correctness", "answer_relevance", "faithfulness",
                "context_precision", "context_recall", "latency",
            ],
            "rag": {
                "enabled": bool(collection),
                "collection": collection,
                "retriever": "hybrid",
                "top_k": 4,
                "chunk_size": 800,
                "chunk_overlap": 120,
            },
        }
        run = client.post("/api/evaluations/run", json={"experiment": experiment}).json()
        finished = wait(client, run["id"])
        summary = finished["summary"]
        print(
            f"     quality {summary.get('avg_quality_score')} · "
            f"failure rate {summary.get('failure_rate')}"
        )

        print("3/6  Diagnosing failures…")
        failures = client.get("/api/failures", params={"run_id": run["id"], "limit": 15}).json()
        for failure in failures["items"]:
            client.post(f"/api/failures/{failure['id']}/diagnose", json={})
        print(f"     diagnosed {len(failures['items'])} failure(s)")

        print("4/6  Creating a follow-up experiment…")
        suggestions = client.get(
            f"/api/evaluations/{run['id']}/improvement-suggestions"
        ).json()
        if suggestions["suggestions"]:
            top = suggestions["suggestions"][0]
            improvement = client.post(
                f"/api/experiments/{finished['experiment_id']}/improve",
                json={
                    "apply": top["apply"],
                    "run_id": run["id"],
                    "rerun_failed_only": False,
                    "auto_run": True,
                },
            ).json()
            print(f"     applied {top['apply']}")
            print("5/6  Re-running…")
            wait(client, improvement["run_id"])
            outcome = client.get(
                f"/api/experiments/{improvement['experiment']['id']}/outcome"
            ).json()
            print(f"     verdict: {outcome.get('verdict', {}).get('label')}")
        else:
            print("     no applicable suggestions; skipping the improvement loop")

        print("6/6  Generating a report…")
        report = client.post(
            "/api/reports", json={"run_id": run["id"], "include_failures": True}
        ).json()
        print(f"     report {report['id']} with {len(report['content']['findings'])} finding(s)")

    print("\nDone. Start the app and open http://localhost:5173/dashboard")


if __name__ == "__main__":
    main()
