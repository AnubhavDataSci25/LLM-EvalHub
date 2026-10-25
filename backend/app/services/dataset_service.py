"""Dataset management: validation, CSV/JSON import, CRUD and versioning.

Import is deliberately forgiving about *column naming* (people export from many
tools) and strict about *content* (a question is mandatory, duplicates are
flagged, oversized files are rejected). Every import produces a validation
report that is stored with the dataset version, so a dataset's provenance stays
inspectable later.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.db.base import new_id
from app.models.dataset import Dataset, DatasetVersion, TestCase
from app.schemas.dataset import (
    DatasetCreate,
    DatasetUpdate,
    DatasetValidationReport,
    TestCaseCreate,
    TestCaseUpdate,
    ValidationIssue,
)

logger = get_logger(__name__)

#: Accepted aliases for each canonical field, lower-cased and punctuation-stripped.
COLUMN_ALIASES: dict[str, set[str]] = {
    "id": {"id", "testcaseid", "caseid", "externalid", "uid", "key"},
    "question": {"question", "query", "input", "prompt", "userinput", "q"},
    "ground_truth": {
        "groundtruth",
        "answer",
        "expectedanswer",
        "reference",
        "referenceanswer",
        "expected",
        "truth",
        "label",
        "output",
    },
    "context": {"context", "reference_context", "retrievedcontext", "passage", "document", "evidence"},
    "category": {"category", "topic", "type", "intent", "domain"},
    "difficulty": {"difficulty", "level", "complexity"},
    "tags": {"tags", "labels", "keywords"},
    "expected_sources": {"expectedsources", "sources", "citations", "expectedcitations"},
    "metadata": {"metadata", "meta", "extra"},
}

_MAX_QUESTION_CHARS = 8000


def _canonical(column: str) -> str | None:
    key = "".join(ch for ch in column.lower().strip() if ch.isalnum())
    for canonical, aliases in COLUMN_ALIASES.items():
        if key in aliases:
            return canonical
    return None


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass
    separator = ";" if ";" in text else ","
    return [part.strip() for part in text.split(separator) if part.strip()]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"value": str(value)}


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def validate_rows(rows: list[dict[str, Any]]) -> tuple[list[TestCaseCreate], DatasetValidationReport]:
    """Normalise raw rows into test cases and produce a validation report."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    accepted: list[TestCaseCreate] = []
    seen_questions: dict[str, int] = {}
    detected: set[str] = set()

    if not rows:
        return [], DatasetValidationReport(
            valid=False,
            total_rows=0,
            accepted_rows=0,
            errors=[ValidationIssue(message="The file contained no data rows.")],
        )

    if len(rows) > settings.max_dataset_rows:
        errors.append(
            ValidationIssue(
                message=(
                    f"{len(rows)} rows exceeds the {settings.max_dataset_rows}-row limit. "
                    "Split the dataset or raise MAX_DATASET_ROWS."
                )
            )
        )
        return [], DatasetValidationReport(
            valid=False, total_rows=len(rows), accepted_rows=0, errors=errors
        )

    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            errors.append(ValidationIssue(row=index, message="Row is not an object."))
            continue

        mapped: dict[str, Any] = {}
        for column, value in raw.items():
            if column is None:
                continue
            detected.add(str(column))
            canonical = _canonical(str(column))
            if canonical and (canonical not in mapped or mapped[canonical] in (None, "")):
                mapped[canonical] = value

        question = str(mapped.get("question") or "").strip()
        if not question:
            errors.append(
                ValidationIssue(
                    row=index,
                    field="question",
                    message="Missing question — every test case needs one.",
                )
            )
            continue
        if len(question) > _MAX_QUESTION_CHARS:
            errors.append(
                ValidationIssue(
                    row=index,
                    field="question",
                    message=f"Question exceeds {_MAX_QUESTION_CHARS} characters.",
                )
            )
            continue

        fingerprint = " ".join(question.lower().split())
        if fingerprint in seen_questions:
            warnings.append(
                ValidationIssue(
                    row=index,
                    field="question",
                    severity="warning",
                    message=f"Duplicate of row {seen_questions[fingerprint]}.",
                )
            )
        else:
            seen_questions[fingerprint] = index

        ground_truth = str(mapped.get("ground_truth") or "").strip() or None
        if not ground_truth:
            warnings.append(
                ValidationIssue(
                    row=index,
                    field="ground_truth",
                    severity="warning",
                    message="No expected answer — correctness and context recall will be unavailable.",
                )
            )

        difficulty = str(mapped.get("difficulty") or "").strip().lower() or None
        if difficulty and difficulty not in {"easy", "medium", "hard", "adversarial"}:
            warnings.append(
                ValidationIssue(
                    row=index,
                    field="difficulty",
                    severity="warning",
                    message=f"Unrecognised difficulty '{difficulty}' — stored as 'medium'.",
                )
            )
            difficulty = "medium"

        try:
            accepted.append(
                TestCaseCreate(
                    id=str(mapped.get("id") or "").strip() or None,
                    question=question,
                    ground_truth=ground_truth,
                    context=str(mapped.get("context") or "").strip() or None,
                    category=str(mapped.get("category") or "").strip() or None,
                    difficulty=difficulty,
                    tags=_as_list(mapped.get("tags")),
                    expected_sources=_as_list(mapped.get("expected_sources")),
                    metadata=_as_dict(mapped.get("metadata")),
                )
            )
        except Exception as exc:  # pragma: no cover - pydantic guard
            errors.append(ValidationIssue(row=index, message=str(exc)))

    with_context = sum(1 for c in accepted if c.context)
    with_truth = sum(1 for c in accepted if c.ground_truth)
    categories = sorted({c.category for c in accepted if c.category})
    difficulty_mix: dict[str, int] = {}
    for case in accepted:
        key = case.difficulty or "unspecified"
        difficulty_mix[key] = difficulty_mix.get(key, 0) + 1

    if accepted and with_context == 0:
        warnings.append(
            ValidationIssue(
                severity="warning",
                message=(
                    "No rows contain context. Faithfulness and context metrics need either "
                    "an inline context column or a RAG collection."
                ),
            )
        )

    report = DatasetValidationReport(
        valid=bool(accepted) and not errors,
        total_rows=len(rows),
        accepted_rows=len(accepted),
        errors=errors,
        warnings=warnings,
        detected_columns=sorted(detected),
        stats={
            "with_context": with_context,
            "with_ground_truth": with_truth,
            "categories": categories,
            "difficulty_mix": difficulty_mix,
            "avg_question_chars": (
                round(sum(len(c.question) for c in accepted) / len(accepted), 1)
                if accepted
                else 0
            ),
        },
    )
    return accepted, report


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValidationFailedError("CSV file has no header row.")
    return list(reader)


def parse_json(content: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationFailedError(f"Invalid JSON file: {exc}") from exc
    if isinstance(payload, dict):
        for key in ("test_cases", "testCases", "data", "rows", "items", "cases"):
            if isinstance(payload.get(key), list):
                return payload[key]
        raise ValidationFailedError(
            "JSON object must contain a list under 'test_cases', 'data', 'rows' or 'items'."
        )
    if isinstance(payload, list):
        return payload
    raise ValidationFailedError("JSON must be a list of objects or an object containing one.")


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------
class DatasetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- read ------------------------------------------------------------
    def get(self, dataset_id: str) -> Dataset:
        dataset = self.db.execute(
            select(Dataset)
            .where(Dataset.id == dataset_id)
            .options(selectinload(Dataset.versions))
        ).scalar_one_or_none()
        if dataset is None:
            raise NotFoundError(f"Dataset '{dataset_id}' was not found.")
        return dataset

    def get_version(self, version_id: str) -> DatasetVersion:
        version = self.db.get(DatasetVersion, version_id)
        if version is None:
            raise NotFoundError(f"Dataset version '{version_id}' was not found.")
        return version

    def resolve_version(self, dataset_id: str, version_id: str | None = None) -> DatasetVersion:
        if version_id:
            version = self.get_version(version_id)
            if version.dataset_id != dataset_id:
                raise ValidationFailedError("Dataset version does not belong to that dataset.")
            return version
        dataset = self.get(dataset_id)
        version = dataset.active_version
        if version is None:
            raise ValidationFailedError("Dataset has no versions.")
        return version

    def list(
        self, *, limit: int = 50, offset: int = 0, search: str | None = None
    ) -> tuple[list[Dataset], int]:
        stmt = select(Dataset).options(selectinload(Dataset.versions))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(Dataset.name.ilike(like))
        total = self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        stmt = stmt.order_by(Dataset.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().unique().all()), int(total)

    def test_cases(
        self, version_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[TestCase]:
        stmt = (
            select(TestCase)
            .where(TestCase.dataset_version_id == version_id)
            .order_by(TestCase.position)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_cases(self, version_id: str) -> int:
        return int(
            self.db.execute(
                select(func.count(TestCase.id)).where(TestCase.dataset_version_id == version_id)
            ).scalar_one()
        )

    def summarise(self, dataset: Dataset) -> dict[str, Any]:
        version = dataset.active_version
        if version is None:
            return {"row_count": 0, "version_count": 0}
        cases = self.test_cases(version.id)
        difficulties: dict[str, int] = {}
        for case in cases:
            key = case.difficulty or "unspecified"
            difficulties[key] = difficulties.get(key, 0) + 1
        return {
            "row_count": len(cases),
            "version_count": len(dataset.versions),
            "categories": sorted({c.category for c in cases if c.category}),
            "difficulties": difficulties,
            "has_context": any(c.context for c in cases),
            "has_ground_truth": any(c.ground_truth for c in cases),
        }

    # -- write -----------------------------------------------------------
    def create(
        self,
        payload: DatasetCreate,
        *,
        source: str = "manual",
        benchmark_pack_key: str | None = None,
        report: DatasetValidationReport | None = None,
    ) -> Dataset:
        cases = payload.test_cases
        if report is None:
            cases, report = validate_rows([c.model_dump() for c in payload.test_cases])
        if not cases:
            raise ValidationFailedError(
                "Dataset contains no valid test cases.",
                details=report.model_dump() if report else None,
            )

        dataset = Dataset(
            id=new_id("ds"),
            name=payload.name.strip(),
            description=payload.description,
            domain=payload.domain,
            tags=payload.tags,
            source=source,
            benchmark_pack_key=benchmark_pack_key,
            current_version=1,
        )
        version = DatasetVersion(
            id=new_id("dv"),
            dataset_id=dataset.id,
            version=1,
            notes="Initial version",
            row_count=len(cases),
            validation_report=report.model_dump() if report else {},
        )
        dataset.versions.append(version)
        self.db.add(dataset)
        self.db.flush()
        self._insert_cases(version, cases)
        self.db.flush()
        logger.info("created dataset %s with %s cases", dataset.id, len(cases))
        return dataset

    def _insert_cases(self, version: DatasetVersion, cases: list[TestCaseCreate]) -> None:
        for position, case in enumerate(cases):
            self.db.add(
                TestCase(
                    id=new_id("tc"),
                    dataset_version_id=version.id,
                    external_id=case.id,
                    question=case.question,
                    ground_truth=case.ground_truth,
                    context=case.context,
                    category=case.category,
                    difficulty=case.difficulty,
                    tags=case.tags,
                    expected_sources=case.expected_sources,
                    extra_metadata=case.metadata,
                    position=position,
                )
            )

    def update(self, dataset_id: str, payload: DatasetUpdate) -> Dataset:
        dataset = self.get(dataset_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(dataset, field, value)
        self.db.flush()
        return dataset

    def delete(self, dataset_id: str) -> None:
        dataset = self.get(dataset_id)
        self.db.delete(dataset)
        self.db.flush()

    def new_version(
        self, dataset_id: str, cases: list[TestCaseCreate], *, notes: str | None = None
    ) -> DatasetVersion:
        """Create a new immutable version — older experiments keep pointing at theirs."""
        dataset = self.get(dataset_id)
        _, report = validate_rows([c.model_dump() for c in cases])
        next_version = max((v.version for v in dataset.versions), default=0) + 1
        version = DatasetVersion(
            id=new_id("dv"),
            dataset_id=dataset.id,
            version=next_version,
            notes=notes or f"Version {next_version}",
            row_count=len(cases),
            validation_report=report.model_dump(),
        )
        self.db.add(version)
        self.db.flush()
        self._insert_cases(version, cases)
        dataset.current_version = next_version
        self.db.flush()
        return version

    def add_case(self, dataset_id: str, payload: TestCaseCreate) -> TestCase:
        version = self.resolve_version(dataset_id)
        position = self.count_cases(version.id)
        case = TestCase(
            id=new_id("tc"),
            dataset_version_id=version.id,
            external_id=payload.id,
            question=payload.question,
            ground_truth=payload.ground_truth,
            context=payload.context,
            category=payload.category,
            difficulty=payload.difficulty,
            tags=payload.tags,
            expected_sources=payload.expected_sources,
            extra_metadata=payload.metadata,
            position=position,
        )
        self.db.add(case)
        version.row_count = position + 1
        self.db.flush()
        return case

    def update_case(self, case_id: str, payload: TestCaseUpdate) -> TestCase:
        case = self.db.get(TestCase, case_id)
        if case is None:
            raise NotFoundError(f"Test case '{case_id}' was not found.")
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            case.extra_metadata = data.pop("metadata") or {}
        for field, value in data.items():
            if value is not None:
                setattr(case, field, value)
        self.db.flush()
        return case

    def delete_case(self, case_id: str) -> None:
        case = self.db.get(TestCase, case_id)
        if case is None:
            raise NotFoundError(f"Test case '{case_id}' was not found.")
        version = self.db.get(DatasetVersion, case.dataset_version_id)
        self.db.delete(case)
        self.db.flush()
        if version:
            version.row_count = self.count_cases(version.id)
            self.db.flush()
