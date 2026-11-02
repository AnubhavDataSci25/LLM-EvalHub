"""SQLAlchemy models. Importing this package registers every table."""

from app.models.analysis import ProviderConfigRecord, Recommendation, Report
from app.models.attribution import AttributionCondition, AttributionRun
from app.models.audit import AuditRun, ModelAvailability
from app.models.audit_log import AuditLog
from app.models.auth import RefreshToken, User, Workspace, WorkspaceMember, WorkspaceProviderKey
from app.models.calibration import CalibrationRun, HumanLabel
from app.models.dataset import Dataset, DatasetVersion, Document, DocumentChunk, TestCase
from app.models.experiment import (
    EvaluationResult,
    EvaluationRun,
    Experiment,
    ExperimentModel,
    Failure,
    MetricResult,
    PromptTemplate,
    PromptVersion,
)
from app.models.job import Job

__all__ = [
    "AuditLog",
    "Job",
    "User",
    "Workspace",
    "WorkspaceMember",
    "RefreshToken",
    "WorkspaceProviderKey",
    "Dataset",
    "DatasetVersion",
    "TestCase",
    "Document",
    "DocumentChunk",
    "Experiment",
    "ExperimentModel",
    "EvaluationRun",
    "EvaluationResult",
    "MetricResult",
    "Failure",
    "PromptTemplate",
    "PromptVersion",
    "Recommendation",
    "Report",
    "ProviderConfigRecord",
    "HumanLabel",
    "CalibrationRun",
    "AttributionRun",
    "AttributionCondition",
    "AuditRun",
    "ModelAvailability",
]
