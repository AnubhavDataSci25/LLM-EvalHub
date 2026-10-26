"""SQLAlchemy models. Importing this package registers every table."""

from app.models.analysis import ProviderConfigRecord, Recommendation, Report
from app.models.attribution import AttributionCondition, AttributionRun
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

__all__ = [
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
]
