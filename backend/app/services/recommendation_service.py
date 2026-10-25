"""Model recommendation engine.

This is decision support based on *measured results in this workspace*, never a
universal model ranking. The pipeline is deliberately transparent:

    collect results -> group by provider/model -> aggregate measured metrics
        -> normalise (min-max across the candidate set)
        -> apply configurable weights
        -> apply hard constraints (latency ceiling, quality floors)
        -> rank, explain, and state the caveats

Rules enforced here:
  * a candidate scored on fewer than `min_sample_size` cases is excluded and the
    exclusion is reported,
  * latency is inverted before weighting (lower is better),
  * the phrase "best model" is never used — recommendations are always scoped to
    the dataset, metrics and constraints that produced them,
  * if no candidate satisfies the constraints, the engine says so rather than
    relaxing them silently.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ValidationFailedError
from app.core.logging import get_logger
from app.db.base import new_id
from app.evaluation.aggregators import aggregate_metric, normalise_weights
from app.evaluation.registry import METRIC_SPECS
from app.evaluation.statistics import (
    bootstrap_ci,
    cohens_dz,
    paired_differences,
    sign_flip_permutation_test,
    significance_verdict,
)
from app.models.analysis import Recommendation
from app.models.experiment import EvaluationResult, EvaluationRun, Experiment
from app.schemas.experiment import RecommendationRequest

logger = get_logger(__name__)

#: Named priority profiles. Weights are always shown to the user and editable.
PROFILES: dict[str, dict[str, float]] = {
    "balanced": {"correctness": 0.35, "faithfulness": 0.30, "answer_relevance": 0.20, "latency": 0.15},
    "quality": {"correctness": 0.45, "faithfulness": 0.30, "answer_relevance": 0.20, "latency": 0.05},
    "faithfulness": {"faithfulness": 0.50, "correctness": 0.25, "context_recall": 0.15, "answer_relevance": 0.10},
    "latency": {"latency": 0.45, "correctness": 0.25, "faithfulness": 0.20, "answer_relevance": 0.10},
}

PROFILE_DESCRIPTIONS = {
    "balanced": "Even weighting between answer quality, grounding and speed.",
    "quality": "Prioritises getting the answer right; tolerates slower responses.",
    "faithfulness": "Prioritises grounding — for RAG and compliance-sensitive use cases.",
    "latency": "Prioritises response time for interactive products, with quality floors.",
    "custom": "User-supplied weights.",
}

RANKABLE_METRICS = [k for k, s in METRIC_SPECS.items() if s.group in {"quality", "retrieval"}]


def _describe_driver(metric: str, detail: dict[str, Any]) -> str:
    """Render one score contributor as readable text for the rationale."""
    label = METRIC_SPECS[metric].label.lower() if metric in METRIC_SPECS else metric
    raw = detail.get("raw")
    if raw is None:
        return label
    if metric == "latency" and isinstance(raw, (int, float)):
        return f"{label} {raw:.0f} ms"
    if isinstance(raw, (int, float)):
        return f"{label} {raw:.2f}"
    return f"{label} {raw}"


def _minmax(values: dict[str, float]) -> dict[str, float]:
    """Min-max normalise across candidates; identical values normalise to 1.0."""
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if high - low < 1e-9:
        return dict.fromkeys(values, 1.0)
    return {k: (v - low) / (high - low) for k, v in values.items()}


class RecommendationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- candidate collection ---------------------------------------------
    def _collect_results(self, payload: RecommendationRequest) -> tuple[list[EvaluationResult], dict[str, Any]]:
        stmt = select(EvaluationResult).options(
            selectinload(EvaluationResult.metrics), selectinload(EvaluationResult.failure)
        )
        scope: dict[str, Any] = {}

        run_ids = list(payload.run_ids)
        if payload.experiment_ids:
            extra = list(
                self.db.execute(
                    select(EvaluationRun.id).where(
                        EvaluationRun.experiment_id.in_(payload.experiment_ids),
                        EvaluationRun.status == "completed",
                    )
                ).scalars()
            )
            run_ids.extend(extra)
            scope["experiment_ids"] = payload.experiment_ids
        if payload.dataset_id:
            experiment_ids = list(
                self.db.execute(
                    select(Experiment.id).where(Experiment.dataset_id == payload.dataset_id)
                ).scalars()
            )
            extra = list(
                self.db.execute(
                    select(EvaluationRun.id).where(
                        EvaluationRun.experiment_id.in_(experiment_ids),
                        EvaluationRun.status == "completed",
                    )
                ).scalars()
            )
            run_ids.extend(extra)
            scope["dataset_id"] = payload.dataset_id

        run_ids = list(dict.fromkeys(run_ids))
        if run_ids:
            stmt = stmt.where(EvaluationResult.run_id.in_(run_ids))
            scope["run_ids"] = run_ids
        else:
            completed = list(
                self.db.execute(
                    select(EvaluationRun.id)
                    .where(EvaluationRun.status == "completed")
                    .order_by(EvaluationRun.created_at.desc())
                    .limit(20)
                ).scalars()
            )
            if not completed:
                raise ValidationFailedError(
                    "No completed evaluation runs are available yet. Run an evaluation first — "
                    "recommendations are only made from measured results."
                )
            stmt = stmt.where(EvaluationResult.run_id.in_(completed))
            scope["run_ids"] = completed
            scope["auto_scoped"] = True

        if payload.providers:
            stmt = stmt.where(EvaluationResult.provider.in_(payload.providers))
            scope["providers"] = payload.providers

        return list(self.db.execute(stmt).scalars().unique().all()), scope

    # -- scoring -----------------------------------------------------------
    def build(self, payload: RecommendationRequest) -> Recommendation:
        results, scope = self._collect_results(payload)
        if not results:
            raise ValidationFailedError(
                "No evaluation results match the selected scope, so no recommendation can be made."
            )

        weights = normalise_weights(
            payload.weights if payload.profile == "custom" and payload.weights
            else (payload.weights or PROFILES.get(payload.profile, PROFILES["balanced"]))
        )

        grouped: dict[str, list[EvaluationResult]] = {}
        for result in results:
            grouped.setdefault(f"{result.provider}/{result.model}", []).append(result)

        candidates: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []

        for key, group in grouped.items():
            sample = group[0]
            completed = [r for r in group if r.status == "completed"]
            errors = [r for r in group if r.status == "error"]
            failures = [r for r in group if r.passed is False]
            latencies = [r.latency_ms for r in completed if r.latency_ms is not None]

            metric_stats = {
                metric: aggregate_metric(group, metric)
                for metric in RANKABLE_METRICS
                if any(m.metric == metric for r in group for m in r.metrics)
            }
            measured = {
                metric: stats["mean"]
                for metric, stats in metric_stats.items()
                if stats["mean"] is not None
            }
            sample_size = max([s["sample_size"] for s in metric_stats.values()] or [0])

            candidate = {
                "key": key,
                "provider": sample.provider,
                "model": sample.model,
                "label": sample.model_label or key,
                "cases": len(group),
                "sample_size": sample_size,
                "metrics": measured,
                "metric_detail": {
                    m: {
                        "mean": s["mean"],
                        "sample_size": s["sample_size"],
                        "kinds": s["kinds"],
                        "judge_models": s["judge_models"],
                    }
                    for m, s in metric_stats.items()
                },
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "p95_latency_ms": (
                    round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2)
                    if latencies
                    else None
                ),
                "failure_rate": round(len(failures) / len(group), 4) if group else None,
                "error_rate": round(len(errors) / len(group), 4) if group else None,
                "runs": sorted({r.run_id for r in group}),
            }

            if sample_size < payload.min_sample_size:
                candidate["excluded_reason"] = (
                    f"Only {sample_size} scored case(s); the minimum is {payload.min_sample_size}."
                )
                excluded.append(candidate)
                continue
            candidates.append(candidate)

        constraints, surviving = self._apply_constraints(candidates, payload)
        excluded.extend(c for c in candidates if c.get("excluded_reason"))

        ranked = self._rank(surviving, weights)
        winner = ranked[0] if ranked else None

        top_two_tied = False
        top_two_note = None
        if len(ranked) >= 2:
            top1 = ranked[0]
            top2 = ranked[1]
            top1_results = grouped.get(top1["key"], [])
            top2_results = grouped.get(top2["key"], [])
            scores1 = {
                r.test_case_id: r.composite_score
                for r in top1_results
                if r.composite_score is not None
            }
            scores2 = {
                r.test_case_id: r.composite_score
                for r in top2_results
                if r.composite_score is not None
            }
            diffs, _ = paired_differences(scores2, scores1)
            if len(diffs) >= 10:
                ci_low, ci_high = bootstrap_ci(diffs)
                p_val = sign_flip_permutation_test(diffs)
                effect_dz = cohens_dz(diffs)
                mean_d = float(sum(diffs) / len(diffs))
                verdict, _ = significance_verdict(
                    len(diffs),
                    mean_d,
                    (ci_low, ci_high),
                    p_val,
                    effect_dz=effect_dz,
                )
                if verdict != "significant":
                    top_two_tied = True
                    top_two_note = (
                        f"The top two models are statistically indistinguishable on this data "
                        f"(p={p_val:.4f}, 95% CI [{ci_low:.3f}, {ci_high:.3f}])."
                    )

        recommendation = Recommendation(
            id=new_id("rec"),
            use_case=payload.use_case,
            profile=payload.profile,
            scope={
                **scope,
                "profile_description": PROFILE_DESCRIPTIONS.get(payload.profile, ""),
                "candidates_considered": len(grouped),
                "candidates_ranked": len(ranked),
                "results_analysed": len(results),
                "top_two_tied": top_two_tied,
            },
            weights=weights,
            constraints=constraints,
            candidates=[*ranked, *excluded],
            recommended_provider=winner["provider"] if winner else None,
            recommended_model=winner["model"] if winner else None,
            recommended_score=winner["weighted_score"] if winner else None,
            rationale=self._rationale(winner, ranked, weights, payload),
            evidence=self._evidence(winner, ranked, payload),
            caveats=self._caveats(
                winner, ranked, excluded, results, payload, top_two_note=top_two_note, db=self.db
            ),
            sample_size=winner["sample_size"] if winner else 0,
        )
        self.db.add(recommendation)
        self.db.flush()
        return recommendation

    def _apply_constraints(
        self, candidates: list[dict[str, Any]], payload: RecommendationRequest
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        constraints = {
            "max_latency_ms": payload.max_latency_ms,
            "min_faithfulness": payload.min_faithfulness,
            "min_correctness": payload.min_correctness,
            "max_failure_rate": payload.max_failure_rate,
            "min_sample_size": payload.min_sample_size,
            "providers": payload.providers or None,
        }
        surviving = []
        for candidate in candidates:
            reasons = []
            latency = candidate.get("avg_latency_ms")
            if payload.max_latency_ms and latency is not None and latency > payload.max_latency_ms:
                reasons.append(
                    f"Average latency {latency:.0f} ms exceeds the {payload.max_latency_ms:.0f} ms ceiling."
                )
            for metric, floor in (
                ("faithfulness", payload.min_faithfulness),
                ("correctness", payload.min_correctness),
            ):
                value = candidate["metrics"].get(metric)
                if floor is not None:
                    if value is None:
                        reasons.append(f"{metric} was never measured, so the floor cannot be verified.")
                    elif value < floor:
                        reasons.append(f"{metric} {value:.2f} is below the {floor:.2f} floor.")
            if payload.max_failure_rate is not None:
                rate = candidate.get("failure_rate")
                if rate is not None and rate > payload.max_failure_rate:
                    reasons.append(
                        f"Failure rate {rate:.0%} exceeds the {payload.max_failure_rate:.0%} ceiling."
                    )
            if reasons:
                candidate["excluded_reason"] = " ".join(reasons)
            else:
                surviving.append(candidate)
        return constraints, surviving

    @staticmethod
    def _rank(candidates: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
        """Score each candidate on the weighted metrics and rank them.

        Normalisation policy:

        * **Quality and retrieval metrics** are already on a 0-1 scale, so their
          measured value is used directly. Min-max scaling across candidates was
          rejected because with two candidates it collapses every metric to 0/1
          and throws away the magnitude of the difference — a 0.90 vs 0.88 gap
          would look identical to 0.90 vs 0.30.
        * **Latency** is unbounded, so it is scored as a ratio against the
          fastest candidate in the set (`fastest / this`). That keeps it in
          (0, 1], rewards being fast in proportion, and stays interpretable.

        Weights are renormalised over the metrics a candidate actually has, and
        `weight_coverage` records how much of the intended weighting was usable.
        """
        if not candidates:
            return []

        latencies = [
            c["avg_latency_ms"] for c in candidates if c.get("avg_latency_ms") is not None
        ]
        fastest = min(latencies) if latencies else None

        for candidate in candidates:
            contributions: dict[str, dict[str, float]] = {}
            active_weight = 0.0
            total = 0.0
            for metric, weight in weights.items():
                if metric == "latency":
                    raw = candidate.get("avg_latency_ms")
                    if raw is None or not fastest:
                        continue
                    scaled = max(0.0, min(1.0, fastest / raw))
                else:
                    raw = candidate["metrics"].get(metric)
                    if raw is None:
                        continue
                    scaled = max(0.0, min(1.0, float(raw)))
                contribution = scaled * weight
                contributions[metric] = {
                    "raw": round(float(raw), 4),
                    "normalized": round(scaled, 4),
                    "weight": round(weight, 4),
                    "contribution": round(contribution, 4),
                }
                active_weight += weight
                total += contribution
            candidate["score_breakdown"] = contributions
            candidate["weighted_score"] = (
                round(total / active_weight, 4) if active_weight > 0 else None
            )
            candidate["weight_coverage"] = round(active_weight, 4)

        scored = [c for c in candidates if c.get("weighted_score") is not None]
        unscored = [c for c in candidates if c.get("weighted_score") is None]
        for candidate in unscored:
            candidate["excluded_reason"] = "None of the weighted metrics were measured for this model."
        scored.sort(key=lambda c: -c["weighted_score"])
        for position, candidate in enumerate(scored, start=1):
            candidate["rank"] = position
        return scored

    @staticmethod
    def _rationale(
        winner: dict[str, Any] | None,
        ranked: list[dict[str, Any]],
        weights: dict[str, float],
        payload: RecommendationRequest,
    ) -> str:
        if winner is None:
            return (
                "No model satisfied the selected constraints on the evaluated data. "
                "Relax a constraint, or run an evaluation that measures the required metrics."
            )
        top_metrics = sorted(
            winner.get("score_breakdown", {}).items(),
            key=lambda kv: -kv[1]["contribution"],
        )[:2]
        drivers = ", ".join(
            _describe_driver(metric, detail) for metric, detail in top_metrics
        )
        runner_up = ranked[1] if len(ranked) > 1 else None
        margin = ""
        if runner_up and runner_up.get("weighted_score") is not None:
            delta = winner["weighted_score"] - runner_up["weighted_score"]
            margin = (
                f" It leads {runner_up['label']} by {delta:.3f} on the weighted score"
                + (" — a narrow margin, so treat the two as comparable." if delta < 0.05 else ".")
            )
        return (
            f"On this evaluation scope, {winner['label']} scores highest under the "
            f"'{payload.profile}' weighting ({winner['weighted_score']:.3f}), measured over "
            f"{winner['sample_size']} scored case(s). The largest contributors were {drivers}."
            + margin
        )

    @staticmethod
    def _evidence(
        winner: dict[str, Any] | None, ranked: list[dict[str, Any]], payload: RecommendationRequest
    ) -> list[str]:
        if winner is None:
            return []
        evidence = [
            f"Evaluated on {winner['cases']} result row(s) across {len(winner['runs'])} run(s)."
        ]
        for metric, value in sorted(winner["metrics"].items()):
            detail = winner["metric_detail"].get(metric, {})
            kinds = ", ".join(detail.get("kinds") or []) or "deterministic"
            evidence.append(
                f"{METRIC_SPECS[metric].label if metric in METRIC_SPECS else metric}: "
                f"{value:.3f} over {detail.get('sample_size', 0)} case(s) ({kinds})."
            )
        if winner.get("avg_latency_ms") is not None:
            evidence.append(
                f"Average latency {winner['avg_latency_ms']:.0f} ms"
                + (f", p95 {winner['p95_latency_ms']:.0f} ms." if winner.get("p95_latency_ms") else ".")
            )
        if winner.get("failure_rate") is not None:
            evidence.append(f"Failure rate {winner['failure_rate']:.0%} on the evaluated cases.")
        for other in ranked[1:4]:
            evidence.append(
                f"Compared against {other['label']}: weighted score {other['weighted_score']:.3f}."
            )
        return evidence

    @staticmethod
    def _caveats(
        winner: dict[str, Any] | None,
        ranked: list[dict[str, Any]],
        excluded: list[dict[str, Any]],
        results: list[EvaluationResult],
        payload: RecommendationRequest,
        top_two_note: str | None = None,
        db: Session | None = None,
    ) -> list[str]:
        caveats = [
            "This recommendation reflects measured behaviour on the selected dataset and "
            "metrics only. It is not a general statement about model quality."
        ]
        if top_two_note:
            caveats.append(top_two_note)
        if winner:
            if winner["sample_size"] < 20:
                caveats.append(
                    f"Sample size is small ({winner['sample_size']} scored cases); differences "
                    "of a few points are unlikely to be meaningful."
                )
            judged_entries = []
            for m_name, detail in winner["metric_detail"].items():
                for j in detail.get("judge_models") or []:
                    judged_entries.append((m_name, j))

            if judged_entries:
                if db is not None:
                    from app.services.calibration_service import CalibrationService

                    cal_service = CalibrationService(db)
                    has_uncalibrated = False
                    for m_name, j_model in judged_entries:
                        if "/" in j_model:
                            j_prov, j_mod = j_model.split("/", 1)
                        else:
                            j_prov, j_mod = "mock", j_model
                        rel = cal_service.get_reliability(j_prov, j_mod, m_name)
                        if rel is None or not rel.get("calibrated"):
                            has_uncalibrated = True
                        else:
                            k_val = rel.get("kappa")
                            ci_str = (
                                f"[{rel['interval'][0]:.2f}, {rel['interval'][1]:.2f}]"
                                if rel.get("interval")
                                else "NA"
                            )
                            interp = rel.get("interpretation") or "calibrated"
                            n_l = rel.get("n_labels", 0)
                            caveats.append(
                                f"Judge calibration for {j_model} ({m_name}): Cohen's kappa = {k_val:.2f} "
                                f"(95% CI {ci_str}, N={n_l}, {interp})."
                            )
                            if k_val is not None and k_val < 0.40:
                                caveats.append(
                                    f"Judge agreement on {m_name} is weak (kappa < 0.40); "
                                    "judge-scored metrics should be treated as weak evidence."
                                )
                    if has_uncalibrated:
                        caveats.append(
                            "The LLM judge has no measured agreement with humans on this data (uncalibrated)."
                        )
                else:
                    judged_names = sorted({j for _, j in judged_entries})
                    caveats.append(
                        "Some metrics were scored by an LLM judge ("
                        + ", ".join(judged_names)
                        + "), which introduces judge bias and run-to-run variance."
                    )
            else:
                caveats.append(
                    "All quality metrics were scored deterministically (lexical), which is "
                    "reproducible but does not capture paraphrase as well as a judge model."
                )
        if len(ranked) < 2:
            caveats.append(
                "Fewer than two models met the criteria, so this is not a comparison — "
                "add another model to the experiment for a meaningful ranking."
            )
        if excluded:
            caveats.append(f"{len(excluded)} candidate(s) were excluded; see the candidate table.")
        if payload.max_latency_ms or payload.min_faithfulness or payload.min_correctness:
            caveats.append("Hard constraints were applied before ranking.")
        return caveats

    def get(self, recommendation_id: str) -> Recommendation:
        from app.core.exceptions import NotFoundError

        recommendation = self.db.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise NotFoundError(f"Recommendation '{recommendation_id}' was not found.")
        return recommendation

    def list(self, *, limit: int = 20) -> list[Recommendation]:
        return list(
            self.db.execute(
                select(Recommendation).order_by(Recommendation.created_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
