"""The improvement loop.

    baseline run -> failures -> diagnosis -> accepted suggestions
        -> follow-up experiment (identical except the applied change)
        -> re-run (optionally only the failed cases)
        -> before/after comparison

The important property is *attribution*: the follow-up experiment differs from
its parent only in the fields the user accepted, and that diff is stored on the
experiment, so an improvement can be traced to a specific change rather than to
an unlabelled bundle of edits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.models.experiment import EvaluationResult, EvaluationRun, Experiment, Failure
from app.schemas.experiment import ImprovementRequest, RunEvaluationRequest
from app.services.comparison_service import ComparisonService
from app.services.evaluation_service import EvaluationService
from app.services.experiment_service import ExperimentService

logger = get_logger(__name__)

#: Which override fields the loop is allowed to apply. Anything else is ignored
#: so a malformed diagnosis can never rewrite an experiment arbitrarily.
APPLICABLE_FIELDS = {
    "top_k",
    "chunk_size",
    "chunk_overlap",
    "retriever",
    "system_prompt",
    "prompt_template",
    "temperature",
    "max_tokens",
    "models",
    "metrics",
    "metric_weights",
    "judge_provider",
    "judge_model",
    "rag_enabled",
    "rag_collection",
    "embedding_backend",
}

FIELD_LABELS = {
    "top_k": "Top K",
    "chunk_size": "Chunk size",
    "chunk_overlap": "Chunk overlap",
    "retriever": "Retriever",
    "system_prompt": "System prompt",
    "prompt_template": "Prompt template",
    "temperature": "Temperature",
    "max_tokens": "Max tokens",
    "models": "Models",
}


class ImprovementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.experiments = ExperimentService(db)
        self.evaluations = EvaluationService(db)
        self.comparisons = ComparisonService(db)

    # -- suggestion collection ---------------------------------------------
    def suggestions_for_run(self, run_id: str) -> dict[str, Any]:
        """Aggregate diagnoses across a run into ranked, applicable changes."""
        failures = list(
            self.db.execute(select(Failure).where(Failure.run_id == run_id)).scalars().all()
        )
        if not failures:
            return {"run_id": run_id, "suggestions": [], "diagnosed": 0, "total_failures": 0}

        tally: dict[str, dict[str, Any]] = {}
        diagnosed = 0
        for failure in failures:
            diagnosis = failure.diagnosis
            if not diagnosis:
                continue
            diagnosed += 1
            for suggestion in diagnosis.get("suggestions", []):
                apply = {
                    k: v for k, v in (suggestion.get("apply") or {}).items() if k in APPLICABLE_FIELDS
                }
                if not apply:
                    continue
                key = f"{suggestion.get('action')}::{list(apply.keys())[0]}::{list(apply.values())[0]}"
                entry = tally.setdefault(
                    key,
                    {
                        "action": suggestion.get("action"),
                        "detail": suggestion.get("llm_detail") or suggestion.get("detail"),
                        "expected_improvement": suggestion.get("expected_improvement"),
                        "apply": apply,
                        "supporting_failures": [],
                        "failure_types": {},
                    },
                )
                entry["supporting_failures"].append(failure.id)
                entry["failure_types"][failure.failure_type] = (
                    entry["failure_types"].get(failure.failure_type, 0) + 1
                )

        suggestions = sorted(
            tally.values(), key=lambda s: -len(s["supporting_failures"])
        )
        for suggestion in suggestions:
            suggestion["support_count"] = len(suggestion["supporting_failures"])
            suggestion["supporting_failures"] = suggestion["supporting_failures"][:25]
        return {
            "run_id": run_id,
            "total_failures": len(failures),
            "diagnosed": diagnosed,
            "undiagnosed": len(failures) - diagnosed,
            "suggestions": suggestions,
        }

    # -- follow-up creation -------------------------------------------------
    def create_followup(
        self, experiment_id: str, payload: ImprovementRequest
    ) -> tuple[Experiment, EvaluationRun | None, dict[str, Any]]:
        experiment = self.experiments.get(experiment_id)
        overrides = {k: v for k, v in (payload.apply or {}).items() if k in APPLICABLE_FIELDS}
        if not overrides:
            raise ValidationFailedError(
                "No applicable changes were supplied. A follow-up experiment must differ from "
                "its baseline in at least one recorded field.",
                details={"allowed_fields": sorted(APPLICABLE_FIELDS)},
            )

        baseline_run = self._resolve_baseline_run(experiment, payload.run_id)
        change_summary = payload.change_summary or self._describe(experiment, overrides)

        followup = self.experiments.clone_with_overrides(
            experiment,
            name=payload.name or f"{experiment.name} — {self._short_change(overrides)}",
            overrides=overrides,
            change_summary=change_summary,
        )

        case_ids: list[str] | None = None
        if payload.rerun_failed_only and baseline_run is not None:
            case_ids = self._failed_case_ids(baseline_run.id, payload.failure_ids)
            if not case_ids:
                logger.info("no failed cases to re-run; running the full dataset")
                case_ids = None

        run = None
        if payload.auto_run:
            run = self.evaluations.create_run(
                RunEvaluationRequest(experiment_id=followup.id, case_ids=case_ids)
            )

        context = {
            "baseline_experiment_id": experiment.id,
            "baseline_run_id": baseline_run.id if baseline_run else None,
            "applied_changes": overrides,
            "change_summary": change_summary,
            "config_diff": self.experiments.diff(experiment, followup),
            "rerun_scope": "failed_cases" if case_ids else "full_dataset",
            "case_count": len(case_ids) if case_ids else None,
        }
        return followup, run, context

    def _resolve_baseline_run(
        self, experiment: Experiment, run_id: str | None
    ) -> EvaluationRun | None:
        if run_id:
            run = self.db.get(EvaluationRun, run_id)
            if run is None:
                raise NotFoundError(f"Run '{run_id}' was not found.")
            return run
        runs = [r for r in experiment.runs if r.status == "completed"]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)[0] if runs else None

    def _failed_case_ids(self, run_id: str, failure_ids: list[str]) -> list[str]:
        stmt = select(EvaluationResult.test_case_id).where(
            EvaluationResult.run_id == run_id, EvaluationResult.passed.is_(False)
        )
        if failure_ids:
            result_ids = list(
                self.db.execute(
                    select(Failure.result_id).where(Failure.id.in_(failure_ids))
                ).scalars()
            )
            stmt = select(EvaluationResult.test_case_id).where(
                EvaluationResult.id.in_(result_ids)
            )
        return sorted(set(self.db.execute(stmt).scalars().all()))

    @staticmethod
    def _short_change(overrides: dict[str, Any]) -> str:
        field, value = next(iter(overrides.items()))
        label = FIELD_LABELS.get(field, field)
        if isinstance(value, str) and len(value) > 24:
            return f"{label} revised"
        if field == "models":
            return "model swap"
        return f"{label} {value}"

    @staticmethod
    def _describe(experiment: Experiment, overrides: dict[str, Any]) -> str:
        parts = []
        for field, value in overrides.items():
            label = FIELD_LABELS.get(field, field)
            before = getattr(experiment, field if field != "embedding_backend" else "embedding_model", None)
            if isinstance(value, str) and len(value) > 40:
                parts.append(f"{label} rewritten")
            elif before is not None and not isinstance(before, (list, dict)):
                parts.append(f"{label}: {before} → {value}")
            else:
                parts.append(f"{label} set to {value}")
        return "; ".join(parts)

    # -- outcome ------------------------------------------------------------
    def outcome(self, experiment_id: str) -> dict[str, Any]:
        """Before/after summary for a follow-up experiment."""
        experiment = self.experiments.get(experiment_id)
        if not experiment.parent_experiment_id:
            raise ValidationFailedError(
                "This experiment has no baseline; before/after comparison needs a parent experiment."
            )
        child_runs = self.comparisons._completed_runs(experiment.id)
        parent_runs = self.comparisons._completed_runs(experiment.parent_experiment_id)
        if not child_runs or not parent_runs:
            return {
                "experiment_id": experiment.id,
                "ready": False,
                "message": "Both the baseline and the follow-up need a completed run before "
                "the comparison is meaningful.",
            }
        summary = self.comparisons.improvement_summary(parent_runs[0].id, child_runs[0].id)
        parent = self.db.get(Experiment, experiment.parent_experiment_id)
        summary.update(
            {
                "ready": True,
                "experiment_id": experiment.id,
                "experiment_name": experiment.name,
                "baseline_experiment_id": experiment.parent_experiment_id,
                "baseline_experiment_name": parent.name if parent else None,
                "change_summary": experiment.change_summary,
            }
        )
        return summary
