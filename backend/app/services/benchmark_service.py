"""Benchmark packs — preconfigured, one-click evaluation scenarios.

A pack is a directory under `benchmarks/` containing `pack.json`, a dataset and
optionally source documents for RAG. Installing a pack creates a real dataset
(and optionally indexes its documents and creates a baseline experiment), so a
user reaches a first evaluation in a couple of clicks.

Packs are read from disk at request time, so a user can drop in their own pack
directory without touching the code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import REPO_DIR
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.dataset import Dataset
from app.schemas.benchmark import BenchmarkPackDetail, BenchmarkPackSummary
from app.schemas.dataset import DatasetCreate
from app.services.dataset_service import DatasetService, validate_rows

logger = get_logger(__name__)

BENCHMARKS_DIR = Path(__file__).resolve().parents[3].parent / "benchmarks"
if not BENCHMARKS_DIR.exists():  # running from an installed layout
    BENCHMARKS_DIR = REPO_DIR / "benchmarks"


@lru_cache(maxsize=1)
def _pack_dirs() -> tuple[Path, ...]:
    if not BENCHMARKS_DIR.exists():
        logger.warning("benchmarks directory not found at %s", BENCHMARKS_DIR)
        return ()
    return tuple(sorted(p for p in BENCHMARKS_DIR.iterdir() if (p / "pack.json").exists()))


def _read_pack(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "pack.json").read_text(encoding="utf-8"))
    dataset_path = directory / manifest.get("dataset", "dataset.json")
    rows: list[dict[str, Any]] = []
    if dataset_path.exists():
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        rows = payload.get("test_cases", payload) if isinstance(payload, dict) else payload
    manifest["_rows"] = rows
    manifest["_dir"] = directory
    return manifest


def load_packs() -> list[dict[str, Any]]:
    return [_read_pack(d) for d in _pack_dirs()]


def load_pack(key: str) -> dict[str, Any]:
    for directory in _pack_dirs():
        if directory.name == key:
            return _read_pack(directory)
    raise NotFoundError(f"Benchmark pack '{key}' was not found.")


def _summary_fields(manifest: dict[str, Any]) -> dict[str, Any]:
    rows = manifest.get("_rows", [])
    difficulty_mix: dict[str, int] = {}
    categories: set[str] = set()
    for row in rows:
        key = str(row.get("difficulty") or "unspecified")
        difficulty_mix[key] = difficulty_mix.get(key, 0) + 1
        if row.get("category"):
            categories.add(str(row["category"]))
    return {
        "key": manifest["key"],
        "name": manifest["name"],
        "description": manifest["description"],
        "use_case": manifest.get("use_case", manifest["key"]),
        "metrics": manifest.get("metrics", []),
        "case_count": len(rows),
        "rag_recommended": bool(manifest.get("rag_recommended")),
        "difficulty_mix": difficulty_mix,
        "categories": sorted(categories),
        "default_config": manifest.get("default_config", {}),
        "metric_notes": manifest.get("metric_notes", {}),
    }


class BenchmarkService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.datasets = DatasetService(db)

    def _installed_id(self, key: str) -> str | None:
        return self.db.execute(
            select(Dataset.id)
            .where(Dataset.benchmark_pack_key == key)
            .order_by(Dataset.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_packs(self) -> list[BenchmarkPackSummary]:
        summaries = []
        for manifest in load_packs():
            fields = _summary_fields(manifest)
            fields["installed_dataset_id"] = self._installed_id(fields["key"])
            summaries.append(BenchmarkPackSummary(**fields))
        return summaries

    def get_pack(self, key: str) -> BenchmarkPackDetail:
        manifest = load_pack(key)
        fields = _summary_fields(manifest)
        fields["installed_dataset_id"] = self._installed_id(key)
        fields["sample_cases"] = manifest.get("_rows", [])[:5]
        return BenchmarkPackDetail(**fields)

    def pack_documents(self, key: str) -> list[Path]:
        manifest = load_pack(key)
        directory: Path = manifest["_dir"]
        return [directory / rel for rel in manifest.get("documents", []) if (directory / rel).exists()]

    def install(self, key: str, *, dataset_name: str | None = None) -> Dataset:
        """Materialise a pack as a real dataset."""
        manifest = load_pack(key)
        rows = manifest.get("_rows", [])
        if not rows:
            raise ValidationFailedError(f"Benchmark pack '{key}' contains no test cases.")
        cases, report = validate_rows(rows)
        payload = DatasetCreate(
            name=dataset_name or f"{manifest['name']}",
            description=manifest.get("description"),
            domain=manifest.get("use_case", key),
            tags=["benchmark", key],
            test_cases=cases,
        )
        dataset = self.datasets.create(
            payload, source="benchmark", benchmark_pack_key=key, report=report
        )
        logger.info("installed benchmark pack %s as dataset %s", key, dataset.id)
        return dataset
