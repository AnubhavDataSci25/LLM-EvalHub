"""Comparison service.

Answers the question the whole platform exists for: *did this change help?*

Two shapes of comparison are supported:

  * **model comparison** — several models inside one run, scored on identical
    inputs, so differences are attributable to the model,
  * **experiment comparison** — several runs against a baseline, with the
    configuration diff shown alongside the metric deltas, so a reader can see
    which change produced which movement.

Deltas are reported per metric with the sample size behind each side. A delta
computed from 3 cases is labelled as such rather than presented as a result.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationFailedError
from app.evaluation.aggregators import group_by_model, summarise_results
from app.evaluation.registry import METRIC_SPECS
from app.evaluation.statistics import analyse_metric, holm_correction
from app.models.experiment import EvaluationResult, EvaluationRun, Experiment
from app.services.evaluation_service import EvaluationService
from app.services.experiment_service import ExperimentService

#: Below this many scored cases on either side, a delta is flagged as low-confidence.
LOW_CONFIDENCE_SAMPLE = 10


def _delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return round(after - before, 4)


def _direction(metric: str, delta: float | None) -> str:
    if delta is None:
        return "unknown"
    if abs(delta) < 0.005:
        return "unchanged"
    spec = METRIC_SPECS.get(metric)
    higher_is_better = spec.higher_is_better if spec else True
    improved = delta > 0 if higher_is_better else delta < 0
    return "improved" if improved else "regressed"


class ComparisonService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.evaluations = EvaluationService(db)
        self.experiments = ExperimentService(db)

    # -- model comparison within a run -------------------------------------
    def compare_models(self, run_id: str) -> dict[str, Any]:
        run = self.evaluations.get_run(run_id)
        experiment = self.db.get(Experiment, run.experiment_id)
        results, _ = self.evaluations.results(run_id)
        if not results:
            return {"run_id": run_id, "models": [], "metrics": [], "rows": []}

        metrics = list(experiment.metrics or []) if experiment else []
        weights = experiment.metric_weights if experiment else None
        rows = []
        for key, group in group_by_model(results).items():
            summary = summarise_results(group, metrics, weights)
            sample = group[0]
            rows.append(
                {
                    "key": key,
                    "provider": sample.provider,
                    "model": sample.model,
                    "label": sample.model_label or key,
                    "cases": len(group),
                    "metrics": {
                        m: {
                            "mean": summary["metrics"][m]["mean"],
                            "sample_size": summary["metrics"][m]["sample_size"],
                            "kinds": summary["metrics"][m]["kinds"],
                        }
                        for m in metrics
                        if m in summary["metrics"]
                    },
                    "avg_latency_ms": summary["avg_latency_ms"],
                    "p95_latency_ms": summary["p95_latency_ms"],
                    "failure_rate": summary["failure_rate"],
                    "error_rate": summary["error_rate"],
                    "avg_composite_score": summary["avg_composite_score"],
                    "failure_breakdown": summary["failure_breakdown"],
                }
            )
        rows.sort(
            key=lambda r: (r["avg_composite_score"] is None, -(r["avg_composite_score"] or 0))
        )
        return {
            "run_id": run_id,
            "experiment_id": run.experiment_id,
            "experiment_name": experiment.name if experiment else None,
            "metrics": metrics,
            "rows": rows,
            "identical_inputs": True,
        }

    # -- run / experiment comparison ---------------------------------------
    def compare_runs(
        self,
        run_ids: list[str],
        *,
        baseline_run_id: str | None = None,
        metrics: list[str] | None = None,
    ) -> dict[str, Any]:
        if len(run_ids) < 1:
            raise ValidationFailedError("Select at least one run to compare.")
        runs = [self.evaluations.get_run(rid) for rid in run_ids]
        incomplete = [r.id for r in runs if r.status != "completed"]

        baseline_id = baseline_run_id or run_ids[0]
        if baseline_id not in run_ids:
            runs.insert(0, self.evaluations.get_run(baseline_id))

        blocks: dict[str, dict[str, Any]] = {}
        results_map: dict[str, list[EvaluationResult]] = {}
        metric_union: list[str] = []
        for run in runs:
            experiment = self.db.get(Experiment, run.experiment_id)
            results, _ = self.evaluations.results(run.id)
            results_map[run.id] = results
            run_metrics = list(experiment.metrics or []) if experiment else []
            for metric in run_metrics:
                if metric not in metric_union:
                    metric_union.append(metric)
            summary = run.summary or summarise_results(
                results, run_metrics, experiment.metric_weights if experiment else None
            )
            blocks[run.id] = {
                "run_id": run.id,
                "status": run.status,
                "experiment_id": run.experiment_id,
                "experiment_name": experiment.name if experiment else None,
                "prompt_label": experiment.prompt_label if experiment else None,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "duration_seconds": run.duration_seconds,
                "models": sorted({f"{r.provider}/{r.model}" for r in results}),
                "summary": summary,
                "case_count": len(results),
            }

        selected_metrics = metrics or metric_union
        baseline = blocks[baseline_id]
        baseline_results = results_map[baseline_id]
        baseline_models = {(r.provider, r.model) for r in baseline_results}

        comparisons = []
        target_run_ids = [r.id for r in runs if r.id != baseline_id]
        if not target_run_ids and len(runs) > 1:
            target_run_ids = [baseline_id]

        for run_id in target_run_ids:
            block = blocks[run_id]
            experiment_diff = []
            base_exp = self.db.get(Experiment, baseline["experiment_id"])
            this_exp = self.db.get(Experiment, block["experiment_id"])
            if base_exp and this_exp and base_exp.id != this_exp.id:
                experiment_diff = self.experiments.diff(base_exp, this_exp)

            block_results = results_map[run_id]
            block_models = {(r.provider, r.model) for r in block_results}
            shared_models = baseline_models & block_models

            use_case_id_only = not shared_models and len(baseline_models) == 1 and len(block_models) == 1

            def get_case_key(r: EvaluationResult, case_only: bool = use_case_id_only) -> str:
                if case_only:
                    return str(r.test_case_id)
                return f"{r.test_case_id}::{r.provider}::{r.model}"

            metric_deltas = []
            for metric in selected_metrics:
                before_block = (baseline["summary"].get("metrics") or {}).get(metric) or {}
                after_block = (block["summary"].get("metrics") or {}).get(metric) or {}
                before_summary, after_summary = before_block.get("mean"), after_block.get("mean")

                # Build paired score dicts
                before_scores: dict[str, float] = {}
                after_scores: dict[str, float] = {}
                for r in baseline_results:
                    if shared_models and (r.provider, r.model) not in shared_models:
                        continue
                    k = get_case_key(r)
                    entry = next((m for m in r.metrics if m.metric == metric), None)
                    if entry and entry.available and entry.normalized_score is not None:
                        before_scores[k] = float(entry.normalized_score)
                    elif entry is not None:
                        before_scores[k] = None

                for r in block_results:
                    if shared_models and (r.provider, r.model) not in shared_models:
                        continue
                    k = get_case_key(r)
                    entry = next((m for m in r.metrics if m.metric == metric), None)
                    if entry and entry.available and entry.normalized_score is not None:
                        after_scores[k] = float(entry.normalized_score)
                    elif entry is not None:
                        after_scores[k] = None

                stats = analyse_metric(before_scores, after_scores)
                before_val = stats["mean_before"] if stats["mean_before"] is not None else before_summary
                after_val = stats["mean_after"] if stats["mean_after"] is not None else after_summary
                delta = stats["mean_diff"] if stats["mean_diff"] is not None else _delta(before_summary, after_summary)
                delta_pp = round(delta * 100, 2) if delta is not None else None

                spec = METRIC_SPECS.get(metric)
                higher_is_better = spec.higher_is_better if spec else True

                if stats["significance"] == "significant" and delta is not None:
                    improved = delta > 0 if higher_is_better else delta < 0
                    direction = "improved" if improved else "regressed"
                elif delta is not None:
                    direction = "unchanged"
                else:
                    direction = "unknown"

                low_confidence = (stats["significance"] == "underpowered")

                metric_deltas.append(
                    {
                        "metric": metric,
                        "label": METRIC_SPECS[metric].label if metric in METRIC_SPECS else metric,
                        "before": before_val,
                        "after": after_val,
                        "delta": delta,
                        "delta_pp": delta_pp,
                        "direction": direction,
                        "sample_size": stats["n_pairs"],
                        "low_confidence": low_confidence,
                        "ci_low": stats["ci_low"],
                        "ci_high": stats["ci_high"],
                        "p_value": stats["p_value"],
                        "effect_size_dz": stats["effect_size_dz"],
                        "n_pairs": stats["n_pairs"],
                        "n_dropped": stats["n_dropped"],
                        "required_n": stats["required_n"],
                        "significance": stats["significance"],
                        "significance_reason": stats["significance_reason"],
                    }
                )

            # Paired latency analysis (lower is better)
            before_lat: dict[str, float] = {}
            after_lat: dict[str, float] = {}
            for r in baseline_results:
                if shared_models and (r.provider, r.model) not in shared_models:
                    continue
                if r.latency_ms is not None:
                    before_lat[get_case_key(r)] = float(r.latency_ms)

            for r in block_results:
                if shared_models and (r.provider, r.model) not in shared_models:
                    continue
                if r.latency_ms is not None:
                    after_lat[get_case_key(r)] = float(r.latency_ms)

            lat_stats = analyse_metric(before_lat, after_lat)
            lat_delta = lat_stats["mean_diff"] if lat_stats["mean_diff"] is not None else _delta(
                baseline["summary"].get("avg_latency_ms"), block["summary"].get("avg_latency_ms")
            )
            if lat_stats["significance"] == "significant" and lat_delta is not None:
                lat_direction = "improved" if lat_delta < 0 else "regressed"
            elif lat_delta is not None:
                lat_direction = "unchanged"
            else:
                lat_direction = "unknown"

            latency_analysis = {
                "metric": "latency",
                "label": "Latency",
                "before": lat_stats["mean_before"],
                "after": lat_stats["mean_after"],
                "delta": lat_delta,
                "delta_ms": round(lat_delta, 2) if lat_delta is not None else None,
                "direction": lat_direction,
                "sample_size": lat_stats["n_pairs"],
                "low_confidence": lat_stats["significance"] == "underpowered",
                "ci_low": lat_stats["ci_low"],
                "ci_high": lat_stats["ci_high"],
                "p_value": lat_stats["p_value"],
                "effect_size_dz": lat_stats["effect_size_dz"],
                "n_pairs": lat_stats["n_pairs"],
                "n_dropped": lat_stats["n_dropped"],
                "required_n": lat_stats["required_n"],
                "significance": lat_stats["significance"],
                "significance_reason": lat_stats["significance_reason"],
            }

            failure_delta = _delta(
                baseline["summary"].get("failure_rate"), block["summary"].get("failure_rate")
            )
            improved_count = sum(1 for d in metric_deltas if d["direction"] == "improved")
            regressed_count = sum(1 for d in metric_deltas if d["direction"] == "regressed")

            comparisons.append(
                {
                    "run_id": run_id,
                    "experiment_name": block["experiment_name"],
                    "metric_deltas": metric_deltas,
                    "latency_delta_ms": lat_delta,
                    "latency_analysis": latency_analysis,
                    "failure_rate_delta": failure_delta,
                    "config_diff": experiment_diff,
                    "improved_metrics": improved_count,
                    "regressed_metrics": regressed_count,
                    "verdict": self._verdict(improved_count, regressed_count, metric_deltas, failure_delta),
                }
            )

        return {
            "baseline_run_id": baseline_id,
            "metrics": selected_metrics,
            "runs": list(blocks.values()),
            "comparisons": comparisons,
            "warnings": (
                [f"Run(s) {', '.join(incomplete)} are not completed; their figures are partial."]
                if incomplete
                else []
            ),
        }

    @staticmethod
    def _verdict(
        improved: int,
        regressed: int,
        metric_deltas: list[dict[str, Any]],
        failure_delta: float | None,
    ) -> dict[str, Any]:
        measured = [d for d in metric_deltas if d.get("delta") is not None]
        if not measured:
            return {
                "label": "not comparable",
                "detail": "No metric was measured on both sides of the comparison.",
                "confidence": "none",
                "low_confidence": True,
            }

        underpowered_count = sum(1 for d in measured if d.get("significance") == "underpowered")
        low_confidence = any(d.get("low_confidence", False) for d in measured)

        if any(d.get("significance") == "significant" for d in measured):
            confidence = "high" if underpowered_count == 0 else "moderate"
        elif underpowered_count > 0:
            confidence = "low"
        else:
            confidence = "high"

        if improved > regressed:
            label = "improvement"
            detail = f"{improved} metric(s) significantly improved, {regressed} regressed."
        elif regressed > improved:
            label = "regression"
            detail = f"{regressed} metric(s) significantly regressed, {improved} improved."
        else:
            label = "mixed"
            if improved == 0 and regressed == 0:
                detail = "No statistically significant change detected across measured metrics."
            else:
                detail = f"{improved} improved and {regressed} regressed — no clear direction."

        if failure_delta is not None and abs(failure_delta) >= 0.01:
            detail += (
                f" Failure rate {'fell' if failure_delta < 0 else 'rose'} by "
                f"{abs(failure_delta) * 100:.1f} percentage points."
            )
        if underpowered_count > 0:
            detail += (
                f" ({underpowered_count} metric(s) are underpowered — sample size is too small "
                "to confirm statistical significance.)"
            )
        elif low_confidence:
            detail += " Sample sizes are small, so treat this as indicative only."

        return {
            "label": label,
            "detail": detail,
            "confidence": confidence,
            "low_confidence": low_confidence,
        }

    # -- model significance within a run -----------------------------------
    def compare_models_significance(
        self, run_id: str, metric: str = "correctness"
    ) -> dict[str, Any]:
        run = self.evaluations.get_run(run_id)
        experiment = self.db.get(Experiment, run.experiment_id)
        results, _ = self.evaluations.results(run_id)
        if not results:
            return {
                "run_id": run_id,
                "experiment_id": run.experiment_id,
                "experiment_name": experiment.name if experiment else None,
                "metric": metric,
                "models": [],
                "pairs": [],
                "matrix": {},
            }

        grouped = group_by_model(results)
        model_keys = sorted(grouped.keys())
        labels = {k: grouped[k][0].model_label or k for k in model_keys}

        scores_by_model: dict[str, dict[str, float | None]] = {}
        for m_key, group in grouped.items():
            scores: dict[str, float | None] = {}
            for r in group:
                entry = next((m for m in r.metrics if m.metric == metric), None)
                if entry and entry.available and entry.normalized_score is not None:
                    scores[r.test_case_id] = float(entry.normalized_score)
                elif entry is not None:
                    scores[r.test_case_id] = None
            scores_by_model[m_key] = scores

        pair_data = []
        raw_p_values = []
        for i in range(len(model_keys)):
            for j in range(i + 1, len(model_keys)):
                ma = model_keys[i]
                mb = model_keys[j]
                stats = analyse_metric(scores_by_model[ma], scores_by_model[mb])
                p_val = stats["p_value"] if stats["p_value"] is not None else 1.0
                pair_data.append((ma, mb, stats))
                raw_p_values.append(p_val)

        adjusted_p_values = holm_correction(raw_p_values)

        pairs = []
        matrix: dict[str, dict[str, Any]] = {k: {} for k in model_keys}
        for (ma, mb, stats), _raw_p, adj_p in zip(pair_data, raw_p_values, adjusted_p_values, strict=False):
            sig = stats["significance"]
            sig_reason = stats["significance_reason"]
            if sig == "significant" and adj_p >= 0.05:
                sig = "not_significant"
                sig_reason = (
                    f"Difference not significant after Holm-Bonferroni correction (p_adj={adj_p:.4f})."
                )

            pair_entry = {
                "model_a": ma,
                "model_a_label": labels[ma],
                "model_b": mb,
                "model_b_label": labels[mb],
                "mean_a": stats["mean_before"],
                "mean_b": stats["mean_after"],
                "mean_diff": stats["mean_diff"],
                "ci_low": stats["ci_low"],
                "ci_high": stats["ci_high"],
                "p_value": stats["p_value"],
                "p_value_adjusted": adj_p,
                "effect_size_dz": stats["effect_size_dz"],
                "n_pairs": stats["n_pairs"],
                "n_dropped": stats["n_dropped"],
                "required_n": stats["required_n"],
                "significance": sig,
                "significance_reason": sig_reason,
            }
            pairs.append(pair_entry)

            matrix[ma][mb] = {
                "mean_diff": stats["mean_diff"],
                "ci_low": stats["ci_low"],
                "ci_high": stats["ci_high"],
                "p_value": stats["p_value"],
                "p_value_adjusted": adj_p,
                "significance": sig,
                "effect_size_dz": stats["effect_size_dz"],
                "n_pairs": stats["n_pairs"],
            }
            matrix[mb][ma] = {
                "mean_diff": -stats["mean_diff"] if stats["mean_diff"] is not None else None,
                "ci_low": -stats["ci_high"] if stats["ci_high"] is not None else None,
                "ci_high": -stats["ci_low"] if stats["ci_low"] is not None else None,
                "p_value": stats["p_value"],
                "p_value_adjusted": adj_p,
                "significance": sig,
                "effect_size_dz": -stats["effect_size_dz"] if stats["effect_size_dz"] is not None else None,
                "n_pairs": stats["n_pairs"],
            }

        return {
            "run_id": run_id,
            "experiment_id": run.experiment_id,
            "experiment_name": experiment.name if experiment else None,
            "metric": metric,
            "models": [{"key": k, "label": labels[k]} for k in model_keys],
            "pairs": pairs,
            "matrix": matrix,
        }

    # -- improvement summary (baseline vs follow-up) -----------------------
    def improvement_summary(self, baseline_run_id: str, followup_run_id: str) -> dict[str, Any]:
        comparison = self.compare_runs(
            [baseline_run_id, followup_run_id], baseline_run_id=baseline_run_id
        )
        block = comparison["comparisons"][0] if comparison["comparisons"] else {}
        return {
            "baseline_run_id": baseline_run_id,
            "followup_run_id": followup_run_id,
            "verdict": block.get("verdict"),
            "metric_deltas": block.get("metric_deltas", []),
            "config_diff": block.get("config_diff", []),
            "latency_delta_ms": block.get("latency_delta_ms"),
            "latency_analysis": block.get("latency_analysis"),
            "failure_rate_delta": block.get("failure_rate_delta"),
            "runs": comparison["runs"],
        }

    def recent_deltas(self, limit: int = 5) -> list[dict[str, Any]]:
        """Dashboard widget: follow-up experiments vs their parent baseline."""
        from sqlalchemy import select

        experiments = list(
            self.db.execute(
                select(Experiment)
                .where(Experiment.parent_experiment_id.is_not(None))
                .order_by(Experiment.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        deltas = []
        for experiment in experiments:
            child_runs = self._completed_runs(experiment.id)
            parent_runs = self._completed_runs(experiment.parent_experiment_id or "")
            if not child_runs or not parent_runs:
                continue
            summary = self.improvement_summary(parent_runs[0].id, child_runs[0].id)
            deltas.append(
                {
                    "experiment_id": experiment.id,
                    "experiment_name": experiment.name,
                    "change_summary": experiment.change_summary,
                    "verdict": summary["verdict"],
                    "metric_deltas": summary["metric_deltas"],
                    "baseline_run_id": parent_runs[0].id,
                    "followup_run_id": child_runs[0].id,
                }
            )
        return deltas

    def _completed_runs(self, experiment_id: str) -> list[EvaluationRun]:
        from sqlalchemy import select

        return list(
            self.db.execute(
                select(EvaluationRun)
                .where(
                    EvaluationRun.experiment_id == experiment_id,
                    EvaluationRun.status == "completed",
                )
                .order_by(EvaluationRun.created_at.desc())
            )
            .scalars()
            .all()
        )
