"""Counterfactual Failure Attribution service.

Orchestrates counterfactual test case evaluation across ORACLE_CONTEXT, NO_CONTEXT,
and optional DISTRACTOR_ONLY conditions to attribute failure causes empirically.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.base import new_id
from app.evaluation.attribution import (
    ALL_VERDICTS,
    VERDICT_GENERATION_CAUSED,
    VERDICT_NOT_ATTRIBUTABLE,
    VERDICT_RETRIEVAL_CAUSED,
    AttributionOutcome,
)
from app.evaluation.judge import JudgeConfig, LLMJudge
from app.evaluation.registry import Evaluator
from app.models.attribution import AttributionCondition, AttributionRun
from app.models.dataset import TestCase
from app.models.experiment import EvaluationResult, Experiment, Failure
from app.providers.registry import get_provider
from app.workflows.attribution_graph import AttributionGraph, AttributionState

logger = get_logger(__name__)

DEFAULT_MAX_CASES = 10
MAX_ALLOWED_CASES = 50


class AttributionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- Read -----------------------------------------------------------------
    def get_attribution(self, failure_id: str) -> AttributionRun | None:
        """Fetch the latest AttributionRun for a failure, if one exists."""
        stmt = (
            select(AttributionRun)
            .where(AttributionRun.failure_id == failure_id)
            .options(selectinload(AttributionRun.conditions))
            .order_by(AttributionRun.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def get_experiment_summary(self, experiment_id: str) -> dict[str, Any]:
        """Aggregate attribution results for an experiment."""
        total_failures = int(
            self.db.execute(
                select(func.count(Failure.id)).where(Failure.experiment_id == experiment_id)
            ).scalar_one()
        )

        runs = list(
            self.db.execute(
                select(AttributionRun)
                .where(AttributionRun.experiment_id == experiment_id)
                .options(selectinload(AttributionRun.conditions))
                .order_by(AttributionRun.created_at.desc())
            )
            .scalars()
            .all()
        )

        verdict_counts = dict.fromkeys(ALL_VERDICTS, 0)
        for run in runs:
            if run.verdict in verdict_counts:
                verdict_counts[run.verdict] += 1
            else:
                verdict_counts[run.verdict] = 1

        total_attributed = len(runs)
        retrieval_count = verdict_counts.get(VERDICT_RETRIEVAL_CAUSED, 0)
        generation_count = verdict_counts.get(VERDICT_GENERATION_CAUSED, 0)

        retrieval_share = (
            round(retrieval_count / total_attributed, 4) if total_attributed > 0 else 0.0
        )
        generation_share = (
            round(generation_count / total_attributed, 4) if total_attributed > 0 else 0.0
        )

        return {
            "experiment_id": experiment_id,
            "total_failures": total_failures,
            "total_attributed": total_attributed,
            "verdict_counts": verdict_counts,
            "retrieval_share": retrieval_share,
            "generation_share": generation_share,
            "items": [self._run_to_dict(r) for r in runs],
        }

    # -- Execution ------------------------------------------------------------
    async def attribute_failure(
        self,
        failure_id: str,
        repeats: int = 1,
        include_distractor: bool = False,
    ) -> AttributionRun:
        """Run counterfactual failure attribution on a single failure."""
        failure = self.db.execute(
            select(Failure)
            .where(Failure.id == failure_id)
            .options(
                selectinload(Failure.result).selectinload(EvaluationResult.metrics),
            )
        ).scalar_one_or_none()

        if failure is None:
            raise NotFoundError(f"Failure '{failure_id}' was not found.")

        result = failure.result
        if result is None:
            raise NotFoundError(f"Result for failure '{failure_id}' was not found.")

        experiment = self.db.get(Experiment, failure.experiment_id)
        test_case = self.db.get(TestCase, result.test_case_id)

        # Resolve gold context from test case
        gold_context: str | None = None
        if test_case:
            if (
                test_case.expected_sources
                and isinstance(test_case.expected_sources, list)
                and len(test_case.expected_sources) > 0
            ):
                gold_context = "\n\n".join(str(s) for s in test_case.expected_sources if s)
            if not gold_context and test_case.context:
                gold_context = test_case.context

        # Set up provider and evaluator
        provider = get_provider(result.provider)
        providers = {result.provider: provider}

        judge = None
        if experiment and experiment.judge_provider and experiment.judge_model:
            try:
                j_prov = get_provider(experiment.judge_provider)
                if j_prov.is_configured:
                    judge = LLMJudge(JudgeConfig(provider=j_prov, model=experiment.judge_model))
            except Exception:
                logger.warning("Could not initialize judge for attribution; using deterministic metrics.")

        selected_metrics = list(experiment.metrics or ["correctness", "faithfulness"]) if experiment else ["correctness"]
        evaluator = Evaluator(selected_metrics, judge=judge)

        graph = AttributionGraph(
            providers=providers,
            evaluator=evaluator,
            timeout_seconds=float(settings.request_timeout_seconds),
        )

        initial_state: AttributionState = {
            "failure_id": failure.id,
            "result_id": result.id,
            "experiment_id": failure.experiment_id,
            "run_id": failure.run_id,
            "test_case_id": result.test_case_id,
            "provider": result.provider,
            "model": result.model,
            "prompt_template": experiment.prompt_template if experiment else "",
            "system_prompt": experiment.system_prompt if experiment else None,
            "temperature": experiment.temperature if experiment else 0.0,
            "max_tokens": experiment.max_tokens if experiment else 512,
            "selected_metrics": selected_metrics,
            "question": result.question,
            "ground_truth": result.ground_truth,
            "gold_context": gold_context,
            "has_gold_context": bool(gold_context and gold_context.strip()),
            "distractor_context": [],
            "original_answer": result.generated_answer,
            "original_context": list(result.retrieved_context or []),
            "original_scores": result.metric_map,
            "original_passed": bool(result.passed),
            "original_error": result.error_kind,
            "repeats": max(1, min(5, repeats)),
            "include_distractor": include_distractor,
        }

        final_state = await graph.run(initial_state)
        outcome: AttributionOutcome = final_state["attribution_outcome"]

        # Persist idempotently: replace any previous AttributionRun for this failure
        self.db.execute(delete(AttributionRun).where(AttributionRun.failure_id == failure.id))
        self.db.flush()

        run_id = new_id("att")
        conditions_summary = {}
        for c_name, agg in (final_state.get("condition_aggregates") or {}).items():
            conditions_summary[c_name] = {
                "repeats": agg.repeats,
                "clean_runs": agg.clean_runs,
                "pass_count": agg.pass_count,
                "pass_rate": agg.pass_rate,
                "passed": agg.passed,
                "avg_scores": agg.avg_scores,
                "error": agg.error,
            }

        att_run = AttributionRun(
            id=run_id,
            failure_id=failure.id,
            result_id=result.id,
            experiment_id=failure.experiment_id,
            run_id=failure.run_id,
            test_case_id=result.test_case_id,
            verdict=outcome.verdict,
            confidence=outcome.confidence,
            reason=outcome.reason,
            evidence=outcome.evidence,
            repeats=outcome.repeats,
            conditions_summary=conditions_summary,
            recommendation=outcome.recommendation,
            status="completed",
        )
        self.db.add(att_run)

        # Add condition trial rows
        specs = final_state.get("trial_specs") or []
        for spec in specs:
            cond_id = new_id("atc")
            cond_row = AttributionCondition(
                id=cond_id,
                attribution_run_id=run_id,
                condition=spec["condition"],
                repeat_index=spec.get("repeat_index", 0),
                context_text=spec.get("context_text"),
                prompt_text=spec.get("rendered_prompt"),
                generated_answer=spec.get("generated_answer"),
                latency_ms=spec.get("latency_ms"),
                scores=spec.get("scores") or {},
                passed=spec.get("passed"),
                error_kind=spec.get("error_kind"),
                error_message=spec.get("error_message"),
                raw_meta={},
            )
            self.db.add(cond_row)

        # Update failure detector and signals to reflect confirmed counterfactual attribution
        failure.signals = {
            **(failure.signals or {}),
            "attribution_verdict": outcome.verdict,
            "attribution_confidence": outcome.confidence,
            "attribution_confirmed": outcome.verdict != VERDICT_NOT_ATTRIBUTABLE,
        }
        if outcome.verdict != VERDICT_NOT_ATTRIBUTABLE:
            failure.detector = "counterfactual"

        self.db.flush()
        self.db.commit()

        # Re-fetch with loaded conditions
        return self.get_attribution(failure.id)  # type: ignore[return-value]

    async def attribute_experiment(
        self,
        experiment_id: str,
        only_categories: list[str] | None = None,
        max_cases: int = DEFAULT_MAX_CASES,
        repeats: int = 1,
        dry_run: bool = False,
        include_distractor: bool = False,
    ) -> dict[str, Any]:
        """Batch-run counterfactual attribution for an experiment with free-tier call caps."""
        experiment = self.db.get(Experiment, experiment_id)
        if experiment is None:
            raise NotFoundError(f"Experiment '{experiment_id}' was not found.")

        # Cap max_cases between 1 and 50
        effective_max = max(1, min(MAX_ALLOWED_CASES, max_cases))
        repeats_clamped = max(1, min(5, repeats))

        stmt = select(Failure).where(Failure.experiment_id == experiment_id)
        if only_categories:
            stmt = stmt.where(Failure.failure_type.in_(only_categories))
        stmt = stmt.order_by(Failure.created_at.desc())
        failures = list(self.db.execute(stmt).scalars().all())

        target_failures = failures[:effective_max]
        target_count = len(target_failures)

        # Estimated provider calls:
        # Conditions requiring LLM generation = 2 (oracle_context, no_context) [+ 1 if include_distractor]
        # (ORIGINAL is already stored; does not call the provider).
        conditions_per_case = 3 if include_distractor else 2
        estimated_calls = target_count * conditions_per_case * repeats_clamped

        if dry_run:
            return {
                "dry_run": True,
                "experiment_id": experiment_id,
                "target_cases": target_count,
                "total_failures": len(failures),
                "estimated_provider_calls": estimated_calls,
                "conditions_per_case": conditions_per_case,
                "repeats": repeats_clamped,
                "max_cases": effective_max,
            }

        attributed_items: list[dict[str, Any]] = []
        for fail in target_failures:
            try:
                run = await self.attribute_failure(
                    failure_id=fail.id,
                    repeats=repeats_clamped,
                    include_distractor=include_distractor,
                )
                attributed_items.append(self._run_to_dict(run))
            except Exception:
                logger.exception("Failed attributing failure %s", fail.id)

        return {
            "dry_run": False,
            "experiment_id": experiment_id,
            "completed_cases": len(attributed_items),
            "target_cases": target_count,
            "total_failures": len(failures),
            "estimated_provider_calls": estimated_calls,
            "items": attributed_items,
        }

    @staticmethod
    def _run_to_dict(run: AttributionRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "failure_id": run.failure_id,
            "result_id": run.result_id,
            "experiment_id": run.experiment_id,
            "run_id": run.run_id,
            "test_case_id": run.test_case_id,
            "verdict": run.verdict,
            "confidence": run.confidence,
            "reason": run.reason,
            "evidence": run.evidence or [],
            "repeats": run.repeats,
            "conditions_summary": run.conditions_summary or {},
            "recommendation": run.recommendation,
            "status": run.status,
            "error": run.error,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "conditions": [
                {
                    "id": c.id,
                    "condition": c.condition,
                    "repeat_index": c.repeat_index,
                    "context_text": c.context_text,
                    "generated_answer": c.generated_answer,
                    "latency_ms": c.latency_ms,
                    "scores": c.scores or {},
                    "passed": c.passed,
                    "error_kind": c.error_kind,
                    "error_message": c.error_message,
                }
                for c in (run.conditions or [])
            ],
        }
