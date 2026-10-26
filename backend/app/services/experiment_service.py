"""Experiment management.

An experiment is the reproducible unit of this platform: dataset version +
prompt + parameters + models + retrieval settings + metric selection. Runs point
at an experiment, so "did my change help?" is answerable by comparing two runs
of two experiments that differ in exactly one recorded field.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.db.base import new_id
from app.evaluation.registry import DEFAULT_METRICS, METRIC_SPECS
from app.models.dataset import Dataset
from app.models.experiment import EvaluationRun, Experiment, ExperimentModel
from app.providers.registry import get_provider
from app.schemas.experiment import ExperimentCreate, ModelSelection, RAGConfig
from app.services.audit_service import AuditService
from app.services.dataset_service import DatasetService

logger = get_logger(__name__)

DEFAULT_PROMPT_TEMPLATE = (
    "Answer the question using the context when it is provided.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)

DEFAULT_SYSTEM_PROMPT = (
    "You are a precise assistant being evaluated for factual accuracy. "
    "Answer from the supplied context. If the context does not contain the answer, "
    "say so plainly rather than guessing. Keep answers concise."
)


def render_prompt(template: str, *, question: str, context: str) -> str:
    """Render a prompt template without failing on unknown placeholders."""
    rendered = template or DEFAULT_PROMPT_TEMPLATE
    for key, value in (("question", question), ("context", context or "(no context provided)")):
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


class ExperimentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.datasets = DatasetService(db)

    # -- read ------------------------------------------------------------
    def get(self, experiment_id: str) -> Experiment:
        experiment = self.db.execute(
            select(Experiment)
            .where(Experiment.id == experiment_id)
            .options(selectinload(Experiment.models), selectinload(Experiment.runs))
        ).scalar_one_or_none()
        if experiment is None:
            raise NotFoundError(f"Experiment '{experiment_id}' was not found.")
        return experiment

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        dataset_id: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Experiment], int]:
        stmt = select(Experiment).options(
            selectinload(Experiment.models), selectinload(Experiment.runs)
        )
        if dataset_id:
            stmt = stmt.where(Experiment.dataset_id == dataset_id)
        if search:
            stmt = stmt.where(Experiment.name.ilike(f"%{search.strip()}%"))
        total = int(
            self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        )
        stmt = stmt.order_by(Experiment.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().unique().all()), total

    def to_read_dict(self, experiment: Experiment) -> dict[str, Any]:
        runs = sorted(experiment.runs, key=lambda r: r.created_at, reverse=True)
        latest = runs[0] if runs else None
        dataset = self.db.get(Dataset, experiment.dataset_id)
        return {
            **{
                column.name: getattr(experiment, column.name)
                for column in Experiment.__table__.columns
            },
            "dataset_name": dataset.name if dataset else None,
            "models": experiment.models,
            "run_count": len(runs),
            "latest_run_id": latest.id if latest else None,
            "latest_run_status": latest.status if latest else None,
            "latest_summary": (latest.summary or {}) if latest else {},
        }

    # -- write -----------------------------------------------------------
    def _validate_models(self, models: list[ModelSelection]) -> None:
        from app.services.audit_service import AuditService

        audit_service = AuditService(self.db)
        seen: set[tuple[str, str]] = set()
        for selection in models:
            key = (selection.provider, selection.model)
            if key in seen:
                raise ValidationFailedError(
                    f"Model '{selection.provider}/{selection.model}' is listed twice."
                )
            seen.add(key)
            provider = get_provider(selection.provider)  # raises for unknown providers
            if not provider.is_configured:
                raise ValidationFailedError(
                    f"Provider '{selection.provider}' is not configured. Add its API key "
                    "in the backend environment, or choose a configured provider.",
                    details={"provider": selection.provider},
                )

            cached = audit_service.get_latest_availability(selection.provider, selection.model)
            if cached is not None:
                if cached.status in ("NOT_FOUND", "NOT_ENTITLED", "INVALID_CREDENTIALS"):
                    raise ValidationFailedError(
                        f"Model '{selection.provider}/{selection.model}' cannot be used: "
                        f"status is {cached.status} ({cached.reason}). Please select an available model.",
                        details={
                            "provider": selection.provider,
                            "model": selection.model,
                            "status": cached.status,
                            "reason": cached.reason,
                        },
                    )
                if not audit_service.is_fresh(cached.checked_at):
                    raise ValidationFailedError(
                        f"Cached availability for model '{selection.provider}/{selection.model}' has expired "
                        f"(checked at {cached.checked_at.isoformat()}). A fresh re-check is required before running evaluations.",
                        details={
                            "provider": selection.provider,
                            "model": selection.model,
                            "checked_at": cached.checked_at.isoformat(),
                        },
                    )
                if cached.status == "RATE_LIMITED":
                    logger.warning(
                        "Selected model '%s/%s' is currently rate limited (retry_after=%s)",
                        selection.provider,
                        selection.model,
                        cached.retry_after,
                    )

    def _validate_metrics(self, metrics: list[str], rag: RAGConfig) -> list[str]:
        metrics = [m for m in metrics if m in METRIC_SPECS] or list(DEFAULT_METRICS)
        return metrics

    def create(self, payload: ExperimentCreate) -> Experiment:
        version = self.datasets.resolve_version(payload.dataset_id, payload.dataset_version_id)
        if self.datasets.count_cases(version.id) == 0:
            raise ValidationFailedError("The selected dataset version has no test cases.")
        self._validate_models(payload.models)
        metrics = self._validate_metrics(payload.metrics, payload.rag)

        if payload.judge.configured:
            judge_provider = get_provider(payload.judge.provider or "")
            if not judge_provider.is_configured:
                raise ValidationFailedError(
                    f"Judge provider '{payload.judge.provider}' is not configured."
                )
            cached_j = AuditService(self.db).get_latest_availability(
                payload.judge.provider or "", payload.judge.model or ""
            )
            if cached_j is not None and cached_j.status in ("NOT_FOUND", "NOT_ENTITLED", "INVALID_CREDENTIALS"):
                raise ValidationFailedError(
                    f"Judge model '{payload.judge.provider}/{payload.judge.model}' is unavailable: {cached_j.status} ({cached_j.reason})."
                )

        experiment = Experiment(
            id=new_id("exp"),
            name=payload.name.strip(),
            description=payload.description,
            dataset_id=payload.dataset_id,
            dataset_version_id=version.id,
            parent_experiment_id=payload.parent_experiment_id,
            origin=payload.origin,
            benchmark_pack_key=payload.benchmark_pack_key,
            system_prompt=payload.system_prompt or DEFAULT_SYSTEM_PROMPT,
            prompt_template=payload.prompt_template or DEFAULT_PROMPT_TEMPLATE,
            prompt_label=payload.prompt_label,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            rag_enabled=payload.rag.enabled,
            rag_collection=payload.rag.collection,
            retriever=payload.rag.retriever,
            chunk_size=payload.rag.chunk_size,
            chunk_overlap=payload.rag.chunk_overlap,
            top_k=payload.rag.top_k,
            embedding_model=payload.rag.embedding_backend,
            metrics=metrics,
            metric_weights=payload.metric_weights,
            judge_provider=payload.judge.provider if payload.judge.configured else None,
            judge_model=payload.judge.model if payload.judge.configured else None,
            tags=payload.tags,
            change_summary=payload.change_summary,
        )
        for selection in payload.models:
            experiment.models.append(
                ExperimentModel(
                    id=new_id("em"),
                    experiment_id=experiment.id,
                    provider=selection.provider,
                    model=selection.model,
                    label=selection.label,
                    params=selection.params,
                )
            )
        self.db.add(experiment)
        self.db.flush()
        logger.info(
            "created experiment %s (%s models, rag=%s)",
            experiment.id,
            len(experiment.models),
            experiment.rag_enabled,
        )
        return experiment

    def delete(self, experiment_id: str) -> None:
        experiment = self.get(experiment_id)
        self.db.delete(experiment)
        self.db.flush()

    def clone_with_overrides(
        self,
        experiment: Experiment,
        *,
        name: str | None = None,
        overrides: dict[str, Any] | None = None,
        change_summary: str | None = None,
    ) -> Experiment:
        """Create a follow-up experiment that differs only in the applied overrides.

        This is the mechanism behind the improvement loop: a diagnosis suggests
        `top_k: 6`, the user accepts, and the follow-up experiment is identical
        except for that one field — which is what makes the before/after
        comparison meaningful.
        """
        overrides = dict(overrides or {})
        models = [
            ModelSelection(
                provider=m.provider, model=m.model, label=m.label, params=dict(m.params or {})
            )
            for m in experiment.models
        ]
        if "models" in overrides and overrides["models"]:
            models = [ModelSelection(**m) if isinstance(m, dict) else m for m in overrides["models"]]

        rag = RAGConfig(
            enabled=bool(overrides.get("rag_enabled", experiment.rag_enabled)),
            collection=overrides.get("rag_collection", experiment.rag_collection),
            retriever=overrides.get("retriever", experiment.retriever),
            chunk_size=int(overrides.get("chunk_size", experiment.chunk_size)),
            chunk_overlap=int(overrides.get("chunk_overlap", experiment.chunk_overlap)),
            top_k=int(overrides.get("top_k", experiment.top_k)),
            embedding_backend=overrides.get("embedding_backend", experiment.embedding_model),
        )
        payload = ExperimentCreate(
            name=name or f"{experiment.name} — follow-up",
            description=experiment.description,
            dataset_id=experiment.dataset_id,
            dataset_version_id=experiment.dataset_version_id,
            models=models,
            metrics=list(overrides.get("metrics", experiment.metrics or [])),
            metric_weights=dict(overrides.get("metric_weights", experiment.metric_weights or {})),
            system_prompt=overrides.get("system_prompt", experiment.system_prompt),
            prompt_template=overrides.get("prompt_template", experiment.prompt_template),
            prompt_label=overrides.get("prompt_label", _next_prompt_label(experiment.prompt_label)),
            temperature=float(overrides.get("temperature", experiment.temperature)),
            max_tokens=int(overrides.get("max_tokens", experiment.max_tokens)),
            rag=rag,
            judge={
                "provider": overrides.get("judge_provider", experiment.judge_provider),
                "model": overrides.get("judge_model", experiment.judge_model),
            },
            tags=list(experiment.tags or []),
            parent_experiment_id=experiment.id,
            origin="improvement",
            benchmark_pack_key=experiment.benchmark_pack_key,
            change_summary=change_summary,
        )
        return self.create(payload)

    def diff(self, left: Experiment, right: Experiment) -> list[dict[str, Any]]:
        """Human-readable configuration differences between two experiments."""
        fields = [
            ("dataset_version_id", "Dataset version"),
            ("prompt_label", "Prompt version"),
            ("system_prompt", "System prompt"),
            ("prompt_template", "Prompt template"),
            ("temperature", "Temperature"),
            ("max_tokens", "Max tokens"),
            ("rag_enabled", "RAG enabled"),
            ("rag_collection", "Collection"),
            ("retriever", "Retriever"),
            ("chunk_size", "Chunk size"),
            ("chunk_overlap", "Chunk overlap"),
            ("top_k", "Top K"),
            ("embedding_model", "Embedding backend"),
            ("judge_model", "Judge model"),
        ]
        differences = []
        for field, label in fields:
            before, after = getattr(left, field), getattr(right, field)
            if before != after:
                differences.append(
                    {
                        "field": field,
                        "label": label,
                        "before": _truncate(before),
                        "after": _truncate(after),
                    }
                )
        left_models = {f"{m.provider}/{m.model}" for m in left.models}
        right_models = {f"{m.provider}/{m.model}" for m in right.models}
        if left_models != right_models:
            differences.append(
                {
                    "field": "models",
                    "label": "Models",
                    "before": sorted(left_models),
                    "after": sorted(right_models),
                }
            )
        return differences

    def runs_for(self, experiment_id: str) -> list[EvaluationRun]:
        return list(
            self.db.execute(
                select(EvaluationRun)
                .where(EvaluationRun.experiment_id == experiment_id)
                .order_by(EvaluationRun.created_at.desc())
            )
            .scalars()
            .all()
        )


def _truncate(value: Any, limit: int = 240) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


def _next_prompt_label(label: str | None) -> str:
    if not label:
        return "v2"
    if label.startswith("v") and label[1:].isdigit():
        return f"v{int(label[1:]) + 1}"
    return f"{label}+1"
