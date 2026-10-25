"""Dataset and benchmark-pack endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.api.deps import DbSession, PageParams
from app.core.config import settings
from app.core.exceptions import ValidationFailedError
from app.schemas.benchmark import (
    BenchmarkInstallRequest,
    BenchmarkPackDetail,
    BenchmarkPackSummary,
)
from app.schemas.common import Acknowledgement
from app.schemas.dataset import (
    DatasetCreate,
    DatasetDetail,
    DatasetImportRequest,
    DatasetRead,
    DatasetUpdate,
    DatasetValidationReport,
    TestCaseCreate,
    TestCaseRead,
    TestCaseUpdate,
)
from app.services.benchmark_service import BenchmarkService
from app.services.dataset_service import (
    DatasetService,
    parse_csv,
    parse_json,
    validate_rows,
)
from app.services.rag_service import RagService

router = APIRouter(prefix="/datasets", tags=["datasets"])
benchmark_router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


def _serialise(service: DatasetService, dataset) -> dict[str, Any]:
    return {
        **{c.name: getattr(dataset, c.name) for c in dataset.__table__.columns},
        **service.summarise(dataset),
    }


# ---------------------------------------------------------------------------
# datasets
# ---------------------------------------------------------------------------
@router.get("", summary="List datasets")
def list_datasets(
    db: DbSession,
    page: PageParams,
    search: str | None = Query(None, description="Filter by name"),
) -> dict[str, Any]:
    service = DatasetService(db)
    datasets, total = service.list(limit=page.limit, offset=page.offset, search=search)
    return {
        "items": [DatasetRead(**_serialise(service, d)) for d in datasets],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.post("", response_model=DatasetDetail, status_code=201, summary="Create a dataset")
def create_dataset(payload: DatasetCreate, db: DbSession) -> DatasetDetail:
    service = DatasetService(db)
    dataset = service.create(payload)
    return _detail(service, dataset)


@router.get("/{dataset_id}", response_model=DatasetDetail, summary="Get a dataset")
def get_dataset(
    dataset_id: str,
    db: DbSession,
    version_id: str | None = Query(None),
    preview: int = Query(200, ge=1, le=2000, description="Max test cases returned"),
) -> DatasetDetail:
    service = DatasetService(db)
    dataset = service.get(dataset_id)
    return _detail(service, dataset, version_id=version_id, limit=preview)


@router.put("/{dataset_id}", response_model=DatasetDetail, summary="Update dataset metadata")
def update_dataset(dataset_id: str, payload: DatasetUpdate, db: DbSession) -> DatasetDetail:
    service = DatasetService(db)
    return _detail(service, service.update(dataset_id, payload))


@router.delete("/{dataset_id}", response_model=Acknowledgement, summary="Delete a dataset")
def delete_dataset(dataset_id: str, db: DbSession) -> Acknowledgement:
    DatasetService(db).delete(dataset_id)
    return Acknowledgement(message="Dataset deleted.", id=dataset_id)


@router.post("/validate", response_model=DatasetValidationReport, summary="Validate rows")
def validate_dataset_rows(payload: DatasetImportRequest) -> DatasetValidationReport:
    _, report = validate_rows(payload.rows)
    return report


@router.post("/{dataset_id}/validate", response_model=DatasetValidationReport, summary="Re-validate a dataset")
def revalidate(dataset_id: str, db: DbSession, version_id: str | None = None) -> DatasetValidationReport:
    service = DatasetService(db)
    version = service.resolve_version(dataset_id, version_id)
    cases = service.test_cases(version.id)
    _, report = validate_rows(
        [
            {
                "id": c.external_id,
                "question": c.question,
                "ground_truth": c.ground_truth,
                "context": c.context,
                "category": c.category,
                "difficulty": c.difficulty,
                "tags": c.tags,
                "expected_sources": c.expected_sources,
                "metadata": c.extra_metadata,
            }
            for c in cases
        ]
    )
    version.validation_report = report.model_dump()
    db.flush()
    return report


@router.post("/import", response_model=DatasetDetail, status_code=201, summary="Import from JSON")
def import_json_dataset(payload: DatasetImportRequest, db: DbSession) -> DatasetDetail:
    cases, report = validate_rows(payload.rows)
    if not cases:
        raise ValidationFailedError(
            "No valid test cases found in the payload.", details=report.model_dump()
        )
    service = DatasetService(db)
    dataset = service.create(
        DatasetCreate(
            name=payload.name,
            description=payload.description,
            domain=payload.domain,
            tags=payload.tags,
            test_cases=cases,
        ),
        source="json",
        report=report,
    )
    return _detail(service, dataset)


@router.post("/upload", response_model=DatasetDetail, status_code=201, summary="Import a CSV or JSON file")
async def upload_dataset(
    db: DbSession,
    file: UploadFile = File(..., description="CSV or JSON file"),
    name: str = Form(...),
    description: str | None = Form(None),
    domain: str | None = Form(None),
) -> DatasetDetail:
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise ValidationFailedError(
            f"File exceeds the {settings.max_upload_bytes / 1e6:.0f} MB upload limit."
        )
    suffix = Path(file.filename or "").suffix.lower()
    if suffix == ".csv":
        rows = parse_csv(content)
        source = "csv"
    elif suffix in {".json", ".jsonl"}:
        rows = parse_json(content)
        source = "json"
    else:
        raise ValidationFailedError(
            f"Unsupported file type '{suffix or file.filename}'. Upload a .csv or .json file."
        )

    cases, report = validate_rows(rows)
    if not cases:
        raise ValidationFailedError(
            "The file contained no valid test cases.", details=report.model_dump()
        )
    service = DatasetService(db)
    dataset = service.create(
        DatasetCreate(
            name=name,
            description=description,
            domain=domain,
            tags=[],
            test_cases=cases,
        ),
        source=source,
        report=report,
    )
    return _detail(service, dataset)


# -- test cases -------------------------------------------------------------
@router.get("/{dataset_id}/cases", summary="List test cases")
def list_cases(
    dataset_id: str,
    db: DbSession,
    page: PageParams,
    version_id: str | None = Query(None),
) -> dict[str, Any]:
    service = DatasetService(db)
    version = service.resolve_version(dataset_id, version_id)
    cases = service.test_cases(version.id, limit=page.limit, offset=page.offset)
    return {
        "items": [_case(c) for c in cases],
        "total": service.count_cases(version.id),
        "limit": page.limit,
        "offset": page.offset,
        "version_id": version.id,
    }


@router.post("/{dataset_id}/cases", response_model=TestCaseRead, status_code=201, summary="Add a test case")
def add_case(dataset_id: str, payload: TestCaseCreate, db: DbSession) -> TestCaseRead:
    return TestCaseRead(**_case(DatasetService(db).add_case(dataset_id, payload)))


@router.put("/cases/{case_id}", response_model=TestCaseRead, summary="Update a test case")
def update_case(case_id: str, payload: TestCaseUpdate, db: DbSession) -> TestCaseRead:
    return TestCaseRead(**_case(DatasetService(db).update_case(case_id, payload)))


@router.delete("/cases/{case_id}", response_model=Acknowledgement, summary="Delete a test case")
def delete_case(case_id: str, db: DbSession) -> Acknowledgement:
    DatasetService(db).delete_case(case_id)
    return Acknowledgement(message="Test case deleted.", id=case_id)


@router.post("/{dataset_id}/versions", summary="Create a new dataset version")
def create_version(
    dataset_id: str, payload: DatasetImportRequest, db: DbSession
) -> dict[str, Any]:
    cases, report = validate_rows(payload.rows)
    if not cases:
        raise ValidationFailedError("No valid rows supplied.", details=report.model_dump())
    version = DatasetService(db).new_version(dataset_id, cases, notes=payload.description)
    return {"version_id": version.id, "version": version.version, "row_count": version.row_count}


# ---------------------------------------------------------------------------
# benchmark packs
# ---------------------------------------------------------------------------
@benchmark_router.get("", response_model=list[BenchmarkPackSummary], summary="List benchmark packs")
def list_packs(db: DbSession) -> list[BenchmarkPackSummary]:
    return BenchmarkService(db).list_packs()


@benchmark_router.get("/{key}", response_model=BenchmarkPackDetail, summary="Get a benchmark pack")
def get_pack(key: str, db: DbSession) -> BenchmarkPackDetail:
    return BenchmarkService(db).get_pack(key)


@benchmark_router.post("/{key}/install", summary="Install a benchmark pack as a dataset")
async def install_pack(key: str, payload: BenchmarkInstallRequest, db: DbSession) -> dict[str, Any]:
    service = BenchmarkService(db)
    dataset = service.install(key, dataset_name=payload.dataset_name)

    documents: list[dict[str, Any]] = []
    collection: str | None = None
    doc_paths = service.pack_documents(key)
    if doc_paths:
        rag = RagService(db)
        collection = f"{key}"
        for path in doc_paths:
            document = rag.register_local_file(path, collection=collection)
            documents.append({"id": document.id, "filename": document.filename})
        pack = service.get_pack(key)
        config = pack.default_config or {}
        await rag.index(
            [d["id"] for d in documents],
            collection=collection,
            chunk_size=int(config.get("chunk_size", settings.default_chunk_size)),
            chunk_overlap=int(config.get("chunk_overlap", settings.default_chunk_overlap)),
        )

    dataset_service = DatasetService(db)
    return {
        "dataset": DatasetRead(**_serialise(dataset_service, dataset)).model_dump(),
        "documents": documents,
        "collection": collection,
        "pack": service.get_pack(key).model_dump(),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _case(case) -> dict[str, Any]:
    return {
        "id": case.id,
        "external_id": case.external_id,
        "question": case.question,
        "ground_truth": case.ground_truth,
        "context": case.context,
        "category": case.category,
        "difficulty": case.difficulty,
        "tags": case.tags or [],
        "expected_sources": case.expected_sources or [],
        "metadata": case.extra_metadata or {},
        "position": case.position,
    }


def _detail(
    service: DatasetService, dataset, *, version_id: str | None = None, limit: int = 200
) -> DatasetDetail:
    version = service.resolve_version(dataset.id, version_id)
    cases = service.test_cases(version.id, limit=limit)
    report = version.validation_report or None
    return DatasetDetail(
        **_serialise(service, dataset),
        versions=[
            {
                "id": v.id,
                "version": v.version,
                "notes": v.notes,
                "row_count": v.row_count,
                "created_at": v.created_at,
                "validation_report": v.validation_report or {},
            }
            for v in dataset.versions
        ],
        test_cases=[TestCaseRead(**_case(c)) for c in cases],
        validation_report=DatasetValidationReport(**report) if report else None,
    )
