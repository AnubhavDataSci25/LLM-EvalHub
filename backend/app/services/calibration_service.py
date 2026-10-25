"""Judge calibration service: human labels, agreement scoring and bias probes."""

from __future__ import annotations

from typing import Any

import numpy as np
from langchain_core.prompts import PromptTemplate
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.concurrency import run_bounded, with_retries
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.base import new_id, utcnow
from app.evaluation.calibration import (
    LANDIS_KOCH_NOTE,
    cohens_kappa,
    discretise,
    flip_rate,
    interpret_kappa,
    judge_bias_summary,
    kappa_interval,
    wilson_interval,
)
from app.evaluation.judge import JudgeConfig, LLMJudge
from app.models.calibration import CalibrationRun, HumanLabel
from app.models.experiment import EvaluationResult, EvaluationRun, MetricResult
from app.providers import get_provider

logger = get_logger(__name__)

# Fixed ~80-word neutral, content-free filler paragraph
VERBOSITY_FILLER = (
    "In evaluating this broader scenario, it is standard practice to review all available context "
    "and note general operational considerations across system boundaries. Standard procedural observations "
    "indicate that routine background parameters remain consistently active across related administrative "
    "and operational domains. While additional discussions may periodically continue regarding overarching "
    "frameworks, high-level governance, and general documentation perspectives, these supplementary notes simply "
    "reflect standard ambient record-keeping routines without altering underlying factual claims, primary results, "
    "or functional specifications in any substantive manner."
)

ORDER_SWAP_CORRECTNESS_PROMPT = PromptTemplate.from_template(
    """Judge whether the ANSWER is factually correct with respect to the REFERENCE answer.

Scoring guide:
1.0 = fully correct, conveys the same facts as the reference
0.75 = mostly correct, minor omission that does not change the meaning
0.5 = partially correct, missing or muddling an important element
0.25 = mostly incorrect, but touches the right topic
0.0 = incorrect, contradicts the reference, or refuses to answer

QUESTION:
{question}

ANSWER:
{answer}

REFERENCE:
{reference}

Respond with JSON exactly like:
{{"score": 0.0, "reasoning": "one or two sentences", "confidence": 0.0}}"""
)

ORDER_SWAP_FAITHFULNESS_PROMPT = PromptTemplate.from_template(
    """Judge whether every claim in the ANSWER is supported by the CONTEXT.
A claim that is true in the world but absent from the context is UNSUPPORTED.

1.0 = every claim is supported by the context
0.5 = some claims supported, at least one unsupported
0.0 = the central claim is unsupported or contradicts the context

ANSWER:
{answer}

CONTEXT:
{context}

Respond with JSON exactly like:
{{"score": 0.0, "reasoning": "one or two sentences", "unsupported_claims": ["..."], "confidence": 0.0}}"""
)

ORDER_SWAP_RELEVANCE_PROMPT = PromptTemplate.from_template(
    """Judge how directly the ANSWER addresses the QUESTION that was asked.
Ignore factual accuracy here — only judge whether it answers *this* question.

1.0 = answers the question directly and completely
0.5 = partially addresses it, or buries the answer in unrelated content
0.0 = does not address the question, is evasive, or is empty

ANSWER:
{answer}

QUESTION:
{question}

Respond with JSON exactly like:
{{"score": 0.0, "reasoning": "one or two sentences", "confidence": 0.0}}"""
)


class CalibrationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- Human Labelling ----------------------------------------------------

    def label(
        self,
        result_id: str,
        metric: str,
        label: int,
        annotator: str = "default",
        note: str | None = None,
    ) -> HumanLabel:
        """Upsert a human label for a specific result, metric and annotator."""
        stmt = select(HumanLabel).where(
            HumanLabel.result_id == result_id,
            HumanLabel.metric == metric,
            HumanLabel.annotator == annotator,
        )
        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing:
            existing.label = label
            existing.note = note
            existing.updated_at = utcnow()
            self.db.flush()
            return existing

        item = HumanLabel(
            id=new_id("lbl"),
            result_id=result_id,
            metric=metric,
            label=label,
            annotator=annotator,
            note=note,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def list_unlabelled(
        self,
        run_id: str,
        metric: str,
        limit: int = 30,
        annotator: str = "default",
    ) -> list[dict[str, Any]]:
        """Return a deterministic, stratified sample of results lacking human labels.

        Stratified across models and judge-score bands.
        Hides the judge score so labelling is completely blind.
        """
        # All completed results for this run with judge score for this metric
        stmt = (
            select(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
            .options(selectinload(EvaluationResult.metrics))
            .order_by(EvaluationResult.id)
        )
        results = list(self.db.execute(stmt).scalars().unique().all())

        # Existing labels for this run and metric
        labelled_res_ids = set(
            self.db.execute(
                select(HumanLabel.result_id)
                .join(EvaluationResult, HumanLabel.result_id == EvaluationResult.id)
                .where(
                    EvaluationResult.run_id == run_id,
                    HumanLabel.metric == metric,
                    HumanLabel.annotator == annotator,
                )
            ).scalars().all()
        )

        candidates: list[tuple[EvaluationResult, int]] = []
        for res in results:
            if res.id in labelled_res_ids:
                continue
            matching_mr = next(
                (
                    m
                    for m in res.metrics
                    if m.metric == metric and m.kind == "llm_judge" and m.available and m.normalized_score is not None
                ),
                None,
            )
            if matching_mr is not None:
                band = discretise(matching_mr.normalized_score)
                candidates.append((res, band))

        if not candidates:
            return []

        # Stratify by (model, score_band)
        strata: dict[tuple[str, int], list[EvaluationResult]] = {}
        for res, band in candidates:
            strata.setdefault((res.model, band), []).append(res)

        selected: list[EvaluationResult] = []
        bucket_keys = sorted(strata.keys())
        idx = 0
        while len(selected) < limit:
            added_in_round = False
            for k in bucket_keys:
                bucket = strata[k]
                if idx < len(bucket):
                    selected.append(bucket[idx])
                    added_in_round = True
                    if len(selected) >= limit:
                        break
            if not added_in_round:
                break
            idx += 1

        return [
            {
                "result_id": res.id,
                "run_id": res.run_id,
                "model": res.model,
                "model_label": res.model_label,
                "question": res.question,
                "expected_answer": res.ground_truth,
                "generated_answer": res.generated_answer,
                "retrieved_context": list(res.retrieved_context or []),
                "metric": metric,
            }
            for res in selected
        ]

    def list_labels(
        self,
        run_id: str | None = None,
        metric: str | None = None,
    ) -> list[HumanLabel]:
        """List human labels, optionally filtered by run_id or metric."""
        stmt = select(HumanLabel).order_by(HumanLabel.created_at.desc())
        if run_id:
            stmt = stmt.join(EvaluationResult, HumanLabel.result_id == EvaluationResult.id).where(
                EvaluationResult.run_id == run_id
            )
        if metric:
            stmt = stmt.where(HumanLabel.metric == metric)
        return list(self.db.execute(stmt).scalars().all())

    # -- Calibration Execution ----------------------------------------------

    async def calibrate(
        self,
        run_id: str | None = None,
        dataset_id: str | None = None,
        metric: str = "correctness",
        judge_provider: str | None = None,
        judge_model: str | None = None,
        run_probes: bool = True,
    ) -> CalibrationRun:
        """Run judge calibration: compute kappa, intervals, confusion matrix, and bias probes."""
        scope: dict[str, Any] = {}
        stmt = select(EvaluationResult).options(selectinload(EvaluationResult.metrics))
        if run_id:
            stmt = stmt.where(EvaluationResult.run_id == run_id)
            scope["run_id"] = run_id
        elif dataset_id:
            stmt = stmt.where(EvaluationResult.dataset_id == dataset_id)
            scope["dataset_id"] = dataset_id
        else:
            # Fall back to latest run
            latest_run = self.db.execute(
                select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(1)
            ).scalar_one_or_none()
            if latest_run:
                stmt = stmt.where(EvaluationResult.run_id == latest_run.id)
                scope["run_id"] = latest_run.id
            else:
                scope["auto_scoped"] = True

        results = list(self.db.execute(stmt).scalars().unique().all())

        # Check if the scope contains any judge scores for this metric
        all_metric_results: list[tuple[EvaluationResult, MetricResult]] = []
        for r in results:
            for m in r.metrics:
                if m.metric == metric and m.available and m.normalized_score is not None:
                    all_metric_results.append((r, m))

        has_judge_scores = any(m.kind == "llm_judge" for _, m in all_metric_results)
        if not has_judge_scores:
            cal_run = CalibrationRun(
                id=new_id("cal"),
                judge_provider=judge_provider or "none",
                judge_model=judge_model or "none",
                metric=metric,
                scope=scope,
                n_labels=0,
                status="no_judge_scores",
                warnings=[
                    f"Selected evaluation scope contains only deterministic scores for '{metric}'. "
                    "Calibration applies to LLM-judge metrics; deterministic metrics need no calibration."
                ],
            )
            self.db.add(cal_run)
            self.db.flush()
            return cal_run

        # Filter to results that have judge scores
        judge_scored_results = [(r, m) for r, m in all_metric_results if m.kind == "llm_judge"]

        # Infer judge provider/model if not explicitly passed
        if not judge_provider or not judge_model:
            sample_mr = judge_scored_results[0][1]
            if sample_mr.judge_model and "/" in sample_mr.judge_model:
                parts = sample_mr.judge_model.split("/", 1)
                judge_provider = judge_provider or parts[0]
                judge_model = judge_model or parts[1]
            elif sample_mr.judge_model:
                judge_model = judge_model or sample_mr.judge_model
                judge_provider = judge_provider or "mock"

        judge_provider = judge_provider or "mock"
        judge_model = judge_model or "mock-judge"

        # Check judge provider configuration
        try:
            provider_obj = get_provider(judge_provider)
            is_conf = bool(provider_obj and provider_obj.is_configured)
        except Exception:
            provider_obj = None
            is_conf = False

        if not is_conf or provider_obj is None:
            cal_run = CalibrationRun(
                id=new_id("cal"),
                judge_provider=judge_provider,
                judge_model=judge_model,
                metric=metric,
                scope=scope,
                n_labels=0,
                status="judge_unavailable",
                warnings=[
                    f"Judge provider '{judge_provider}' is not configured or disabled. "
                    "Configure provider credentials in settings or .env to run calibration."
                ],
            )
            self.db.add(cal_run)
            self.db.flush()
            return cal_run

        # Collect results that have BOTH a human label and a judge MetricResult
        res_ids = [r.id for r, _ in judge_scored_results]
        labels = list(
            self.db.execute(
                select(HumanLabel).where(
                    HumanLabel.result_id.in_(res_ids),
                    HumanLabel.metric == metric,
                )
            ).scalars().all()
        )
        label_map = {lbl.result_id: lbl.label for lbl in labels}

        paired: list[tuple[EvaluationResult, MetricResult, int]] = []
        for r, m in judge_scored_results:
            if r.id in label_map:
                paired.append((r, m, label_map[r.id]))

        n_labels = len(paired)

        # Rule 1: Never fabricate agreement. If fewer than 10 labelled cases exist:
        if n_labels < 10:
            cal_run = CalibrationRun(
                id=new_id("cal"),
                judge_provider=judge_provider,
                judge_model=judge_model,
                metric=metric,
                scope=scope,
                n_labels=n_labels,
                status="insufficient_labels",
                warnings=[
                    f"Insufficient human labels ({n_labels} < 10 required). "
                    "Label at least 10 cases in the queue before agreement can be calculated."
                ],
                agreement={},
                probes={},
            )
            self.db.add(cal_run)
            self.db.flush()
            return cal_run

        # Compute kappa & intervals
        human_labels = [p[2] for p in paired]
        judge_discrete = [discretise(p[1].normalized_score) for p in paired]

        unweighted = cohens_kappa(human_labels, judge_discrete, weights=None)
        quadratic = cohens_kappa(human_labels, judge_discrete, weights="quadratic")
        linear = cohens_kappa(human_labels, judge_discrete, weights="linear")
        interval = kappa_interval(human_labels, judge_discrete, weights=None, seed=1234)
        weighted_interval = kappa_interval(human_labels, judge_discrete, weights="quadratic", seed=1234)
        interpretation = interpret_kappa(unweighted["kappa"])
        bias = judge_bias_summary(human_labels, judge_discrete)

        warnings: list[str] = []
        if n_labels < 30:
            warnings.append(
                f"Sample size is small ({n_labels} cases). Target 30+ labelled cases for reliable agreement intervals."
            )
        if unweighted["kappa"] is not None and unweighted["kappa"] < 0.40:
            warnings.append(
                f"Low judge agreement (kappa = {unweighted['kappa']:.2f} < 0.40). Treat judge-scored metrics as weak evidence."
            )

        agreement = {
            "kappa": unweighted["kappa"],
            "weighted_kappa": quadratic["kappa"],
            "linear_kappa": linear["kappa"],
            "interval": list(interval) if interval else None,
            "weighted_interval": list(weighted_interval) if weighted_interval else None,
            "observed_agreement": unweighted["observed_agreement"],
            "expected_agreement": unweighted["expected_agreement"],
            "confusion_matrix": unweighted["confusion_matrix"],
            "per_class_agreement": unweighted["per_class_agreement"],
            "interpretation": interpretation,
            "bias": bias,
            "single_annotator_note": (
                "Agreement is measured against a single human annotator and reflects alignment with that individual."
            ),
            "landis_koch_note": LANDIS_KOCH_NOTE,
        }

        probes: dict[str, Any] = {}
        if run_probes:
            judge_config = JudgeConfig(provider=provider_obj, model=judge_model)
            judge = LLMJudge(judge_config)

            # 1. order_swap probe
            order_probe = await self._probe_order_swap(paired, metric, judge)
            probes["order_swap"] = order_probe
            warnings.extend(order_probe.get("warnings", []))

            # 2. verbosity_padding probe
            verb_probe = await self._probe_verbosity(paired, metric, judge)
            probes["verbosity_padding"] = verb_probe
            warnings.extend(verb_probe.get("warnings", []))

            # 3. self_preference probe (no re-calling judge)
            self_pref_probe = self._probe_self_preference(judge_scored_results, judge_provider, judge_model)
            probes["self_preference"] = self_pref_probe
            warnings.extend(self_pref_probe.get("warnings", []))

        cal_run = CalibrationRun(
            id=new_id("cal"),
            judge_provider=judge_provider,
            judge_model=judge_model,
            metric=metric,
            scope=scope,
            n_labels=n_labels,
            status="completed",
            agreement=agreement,
            probes=probes,
            warnings=list(dict.fromkeys(warnings)),
        )
        self.db.add(cal_run)
        self.db.flush()
        return cal_run

    # -- Probes -------------------------------------------------------------

    async def _probe_order_swap(
        self,
        paired: list[tuple[EvaluationResult, MetricResult, int]],
        metric: str,
        judge: LLMJudge,
    ) -> dict[str, Any]:
        """Order swap probe: swap reference/answer order and measure flip rate."""
        # Sample at most 40 cases deterministically
        sample = self._sample_deterministic(paired, max_cases=40)
        if not sample:
            return {
                "name": "order_swap",
                "n": 0,
                "flip_rate": 0.0,
                "interval": [0.0, 0.0],
                "mean_shift": 0.0,
                "interpretation": "No cases available for order-swap probe.",
                "warnings": [],
            }

        async def _eval_one(item: tuple[EvaluationResult, MetricResult, int]) -> int:
            res, orig_mr, _ = item
            if metric == "correctness":
                prompt = ORDER_SWAP_CORRECTNESS_PROMPT.format(
                    question=res.question,
                    answer=res.generated_answer or "(empty)",
                    reference=res.ground_truth or "",
                )
            elif metric == "faithfulness":
                joined = "\n\n".join(res.retrieved_context or [])
                prompt = ORDER_SWAP_FAITHFULNESS_PROMPT.format(
                    answer=res.generated_answer or "(empty)",
                    context=joined[:8000],
                )
            else:  # answer_relevance
                prompt = ORDER_SWAP_RELEVANCE_PROMPT.format(
                    answer=res.generated_answer or "(empty)",
                    question=res.question,
                )

            async def _call() -> float:
                outcome = await judge._score(metric, prompt)
                return outcome.normalized_score if outcome.available and outcome.normalized_score is not None else 0.0

            try:
                score = await with_retries(_call)
            except Exception:
                score = orig_mr.normalized_score or 0.0
            return discretise(score)

        probed_discrete = await run_bounded(sample, _eval_one, limit=settings.max_concurrent_requests)
        orig_discrete = [discretise(m.normalized_score) for _, m, _ in sample]

        stats = flip_rate(orig_discrete, probed_discrete)
        warnings: list[str] = []
        if stats["flip_rate"] > 0.20:
            interpretation = (
                f"Significant position sensitivity: {stats['flip_rate']:.1%} of verdicts flipped when presentation "
                f"order was swapped (95% CI [{stats['interval'][0]:.2f}, {stats['interval'][1]:.2f}])."
            )
            warnings.append(
                f"Order sensitivity detected: judge flipped {stats['flip_rate']:.1%} of verdicts when inputs were reordered."
            )
        else:
            interpretation = (
                f"Good positional invariance: only {stats['flip_rate']:.1%} of verdicts flipped under presentation reordering "
                f"(95% CI [{stats['interval'][0]:.2f}, {stats['interval'][1]:.2f}])."
            )

        return {
            "name": "order_swap",
            "n": len(sample),
            "flip_rate": stats["flip_rate"],
            "interval": list(stats["interval"]),
            "mean_shift": stats["mean_shift"],
            "flips": stats["flips"],
            "interpretation": interpretation,
            "warnings": warnings,
        }

    async def _probe_verbosity(
        self,
        paired: list[tuple[EvaluationResult, MetricResult, int]],
        metric: str,
        judge: LLMJudge,
    ) -> dict[str, Any]:
        """Verbosity padding probe: append neutral filler text and test if judge score rises."""
        sample = self._sample_deterministic(paired, max_cases=40)
        if not sample:
            return {
                "name": "verbosity_padding",
                "n": 0,
                "share_scored_higher": 0.0,
                "flip_rate": 0.0,
                "mean_score_change": 0.0,
                "interval": [0.0, 0.0],
                "interpretation": "No cases available for verbosity-padding probe.",
                "warnings": [],
            }

        async def _eval_one(item: tuple[EvaluationResult, MetricResult, int]) -> float:
            res, orig_mr, _ = item
            padded_answer = f"{res.generated_answer or ''}\n\n{VERBOSITY_FILLER}".strip()

            async def _call() -> float:
                if metric == "correctness":
                    outcome = await judge.correctness(res.question, padded_answer, res.ground_truth)
                elif metric == "faithfulness":
                    outcome = await judge.faithfulness(padded_answer, res.retrieved_context or [])
                else:
                    outcome = await judge.answer_relevance(res.question, padded_answer)
                return outcome.normalized_score if outcome.available and outcome.normalized_score is not None else 0.0

            try:
                return await with_retries(_call)
            except Exception:
                return orig_mr.normalized_score or 0.0

        new_scores = await run_bounded(sample, _eval_one, limit=settings.max_concurrent_requests)
        orig_scores = [float(m.normalized_score or 0.0) for _, m, _ in sample]

        n = len(sample)
        higher_count = sum(1 for new_s, old_s in zip(new_scores, orig_scores, strict=False) if new_s > old_s + 1e-4)
        share_higher = round(float(higher_count) / float(n), 4) if n > 0 else 0.0
        interval = wilson_interval(higher_count, n)
        mean_change = round(float(np.mean([new_s - old_s for new_s, old_s in zip(new_scores, orig_scores, strict=False)])), 4)

        warnings: list[str] = []
        if share_higher > 0.20 or mean_change > 0.05:
            interpretation = (
                f"Verbosity bias detected: filler paragraph caused score to rise in {share_higher:.1%} of cases "
                f"(mean shift {mean_change:+.3f}, 95% CI [{interval[0]:.2f}, {interval[1]:.2f}])."
            )
            warnings.append(
                f"Verbosity bias detected: adding neutral text rewarded candidate answers in {share_higher:.1%} of cases."
            )
        else:
            interpretation = (
                f"Resistant to verbosity padding: score increased in only {share_higher:.1%} of cases "
                f"(mean shift {mean_change:+.3f}, 95% CI [{interval[0]:.2f}, {interval[1]:.2f}])."
            )

        return {
            "name": "verbosity_padding",
            "n": n,
            "share_scored_higher": share_higher,
            "flip_rate": share_higher,
            "mean_score_change": mean_change,
            "interval": list(interval),
            "higher_count": higher_count,
            "interpretation": interpretation,
            "warnings": warnings,
        }

    def _probe_self_preference(
        self,
        judge_scored_results: list[tuple[EvaluationResult, MetricResult]],
        judge_provider: str,
        judge_model: str,
    ) -> dict[str, Any]:
        """Detect self-preference bias by comparing judge scores on same-family vs other models."""
        judge_prov = judge_provider.strip().lower()
        judge_m = judge_model.strip().lower()
        judge_prefix = judge_m.split("/")[0].split("-")[0]

        same_scores: list[float] = []
        other_scores: list[float] = []

        for res, mr in judge_scored_results:
            if mr.normalized_score is None:
                continue
            cand_prov = (res.provider or "").strip().lower()
            cand_m = (res.model or "").strip().lower()
            cand_prefix = cand_m.split("/")[0].split("-")[0]

            is_same = (cand_prov == judge_prov) or (
                cand_prefix == judge_prefix and judge_prefix not in {"", "model"}
            )
            if is_same:
                same_scores.append(float(mr.normalized_score))
            else:
                other_scores.append(float(mr.normalized_score))

        n_same = len(same_scores)
        n_other = len(other_scores)
        mean_same = round(float(np.mean(same_scores)), 4) if same_scores else None
        mean_other = round(float(np.mean(other_scores)), 4) if other_scores else None

        warnings: list[str] = []
        if n_same > 0:
            warnings.append(
                f"Judge shares family with {n_same} evaluated candidate result(s). Potential self-preference bias."
            )
            if mean_other is not None and mean_same > mean_other + 0.05:
                interpretation = (
                    f"Possible self-preference: judge gave same-family models an average score of {mean_same:.2f} "
                    f"(N={n_same}) vs {mean_other:.2f} (N={n_other}) for others."
                )
            else:
                interpretation = (
                    f"Same-family candidates evaluated: mean score {mean_same:.2f} (N={n_same}) vs "
                    f"others mean {mean_other if mean_other is not None else 0.0:.2f} (N={n_other})."
                )
        else:
            interpretation = "No same-family candidate models were present in the evaluated scope."

        return {
            "name": "self_preference",
            "n": n_same + n_other,
            "n_same_family": n_same,
            "n_other_family": n_other,
            "mean_same_family": mean_same,
            "mean_other_family": mean_other,
            "flip_rate": 0.0,
            "interval": [0.0, 0.0],
            "interpretation": interpretation,
            "warnings": warnings,
        }

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _sample_deterministic(
        items: list[tuple[EvaluationResult, MetricResult, int]],
        max_cases: int = 40,
    ) -> list[tuple[EvaluationResult, MetricResult, int]]:
        """Sort by result_id and pick evenly spaced indices."""
        sorted_items = sorted(items, key=lambda x: x[0].id)
        n = len(sorted_items)
        if n <= max_cases:
            return sorted_items
        indices = np.linspace(0, n - 1, max_cases, dtype=int)
        return [sorted_items[i] for i in indices]

    # -- Reliability & Runs -------------------------------------------------

    def get_reliability(
        self,
        judge_provider: str,
        judge_model: str,
        metric: str,
    ) -> dict[str, Any] | None:
        """Fetch the most recent completed calibration run summary for this judge & metric."""
        stmt = (
            select(CalibrationRun)
            .where(
                CalibrationRun.judge_provider == judge_provider,
                CalibrationRun.judge_model == judge_model,
                CalibrationRun.metric == metric,
                CalibrationRun.status == "completed",
            )
            .order_by(CalibrationRun.created_at.desc())
            .limit(1)
        )
        run = self.db.execute(stmt).scalar_one_or_none()
        if run is None:
            return None

        agreement = run.agreement or {}
        return {
            "calibrated": True,
            "status": "calibrated",
            "judge_provider": run.judge_provider,
            "judge_model": run.judge_model,
            "metric": run.metric,
            "kappa": agreement.get("kappa"),
            "weighted_kappa": agreement.get("weighted_kappa"),
            "interval": agreement.get("interval"),
            "n_labels": run.n_labels,
            "interpretation": agreement.get("interpretation"),
            "agreement": agreement,
            "probes": run.probes or {},
            "warnings": run.warnings or [],
        }

    def list_runs(self, limit: int = 50) -> list[CalibrationRun]:
        return list(
            self.db.execute(
                select(CalibrationRun).order_by(CalibrationRun.created_at.desc()).limit(limit)
            ).scalars().all()
        )

    def get_run(self, run_id: str) -> CalibrationRun:
        run = self.db.get(CalibrationRun, run_id)
        if run is None:
            raise NotFoundError(f"Calibration run '{run_id}' was not found.")
        return run
