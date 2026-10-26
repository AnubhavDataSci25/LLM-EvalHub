"""Counterfactual failure attribution rules.

This module provides pure, unit-testable attribution logic without database dependencies.
Given an original failed work unit and counterfactual evaluation results under:
  1. ORACLE_CONTEXT (replacing retrieved context with gold context),
  2. NO_CONTEXT (empty context to test parametric memory),
  3. (Optional) DISTRACTOR_ONLY (top-k non-gold chunks),
it determines empirically whether the failure was caused by retrieval, generation,
or parametric hallucination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.failure_detector import FailureThresholds

VERDICT_RETRIEVAL_CAUSED = "RETRIEVAL_CAUSED"
VERDICT_GENERATION_CAUSED = "GENERATION_CAUSED"
VERDICT_PARAMETRIC_KNOWLEDGE = "PARAMETRIC_KNOWLEDGE"
VERDICT_NOT_CONTEXT_DEPENDENT = "NOT_CONTEXT_DEPENDENT"
VERDICT_NOT_ATTRIBUTABLE = "NOT_ATTRIBUTABLE"

ALL_VERDICTS = [
    VERDICT_RETRIEVAL_CAUSED,
    VERDICT_GENERATION_CAUSED,
    VERDICT_PARAMETRIC_KNOWLEDGE,
    VERDICT_NOT_CONTEXT_DEPENDENT,
    VERDICT_NOT_ATTRIBUTABLE,
]

CONDITION_ORIGINAL = "original"
CONDITION_ORACLE_CONTEXT = "oracle_context"
CONDITION_NO_CONTEXT = "no_context"
CONDITION_DISTRACTOR_ONLY = "distractor_only"


@dataclass(slots=True)
class ConditionExecutionResult:
    """Outcome of one execution trial for a condition."""

    condition: str
    repeat_index: int = 0
    generated_answer: str | None = None
    scores: dict[str, float | None] = field(default_factory=dict)
    latency_ms: float | None = None
    error_kind: str | None = None
    error_message: str | None = None
    passed: bool = False


@dataclass(slots=True)
class ConditionAggregate:
    """Aggregated stats across N repeat trials for one condition."""

    condition: str
    repeats: int
    clean_runs: int
    pass_count: int
    pass_rate: float
    passed: bool
    avg_scores: dict[str, float | None]
    error: str | None = None
    answers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AttributionOutcome:
    """Structured verdict and evidence from counterfactual attribution."""

    verdict: str
    confidence: float
    reason: str
    evidence: list[str] = field(default_factory=list)
    condition_passes: dict[str, bool] = field(default_factory=dict)
    condition_pass_rates: dict[str, float] = field(default_factory=dict)
    condition_scores: dict[str, dict[str, float | None]] = field(default_factory=dict)
    repeats: int = 1
    recommendation: str = ""
    signals: dict[str, Any] = field(default_factory=dict)


def evaluate_trial_pass(
    scores: dict[str, float | None],
    thresholds: FailureThresholds | None = None,
    error: str | None = None,
    answer: str | None = None,
) -> bool:
    """Determine whether a single trial passes using configured thresholds."""
    if error:
        return False
    if not (answer or "").strip():
        return False

    th = thresholds or FailureThresholds()
    correctness = scores.get("correctness")
    faithfulness = scores.get("faithfulness")

    # If correctness is available, it must meet or exceed the threshold
    if correctness is not None and correctness < th.correctness:
        return False

    # If faithfulness is available, it must meet or exceed the threshold
    if faithfulness is not None and faithfulness < th.faithfulness:
        return False

    # If neither correctness nor faithfulness was computed, inspect answer relevance
    if correctness is None and faithfulness is None:
        relevance = scores.get("answer_relevance")
        if relevance is not None and relevance < th.answer_relevance:
            return False

    return True


def aggregate_condition_trials(
    condition: str,
    trials: list[ConditionExecutionResult],
    thresholds: FailureThresholds | None = None,
) -> ConditionAggregate:
    """Aggregate N trials of a condition into a single pass/fail verdict and summary."""
    th = thresholds or FailureThresholds()
    if not trials:
        return ConditionAggregate(
            condition=condition,
            repeats=0,
            clean_runs=0,
            pass_count=0,
            pass_rate=0.0,
            passed=False,
            avg_scores={},
            error="No trials recorded",
        )

    clean_trials = [t for t in trials if not t.error_kind]
    first_error = next((f"{t.error_kind}: {t.error_message}" for t in trials if t.error_kind), None)

    pass_count = 0
    all_scores: dict[str, list[float]] = {}
    answers = []

    for trial in trials:
        if trial.generated_answer:
            answers.append(trial.generated_answer)
        is_pass = evaluate_trial_pass(
            trial.scores,
            th,
            error=trial.error_kind,
            answer=trial.generated_answer,
        )
        if is_pass:
            pass_count += 1
        for metric, val in trial.scores.items():
            if val is not None:
                all_scores.setdefault(metric, []).append(float(val))

    repeats = len(trials)
    pass_rate = pass_count / repeats if repeats > 0 else 0.0
    # Condition passes if majority (>= 50%) of trials pass
    passed = pass_rate >= 0.5 and len(clean_trials) > 0

    avg_scores = {
        metric: round(sum(vals) / len(vals), 4) if vals else None
        for metric, vals in all_scores.items()
    }

    return ConditionAggregate(
        condition=condition,
        repeats=repeats,
        clean_runs=len(clean_trials),
        pass_count=pass_count,
        pass_rate=round(pass_rate, 4),
        passed=passed,
        avg_scores=avg_scores,
        error=first_error if len(clean_trials) == 0 else None,
        answers=answers,
    )


def compute_attribution(
    *,
    original_pass: bool,
    oracle_pass: bool,
    no_context_pass: bool,
    has_gold_context: bool,
    condition_errors: dict[str, str | None] | None = None,
    repeats: int = 1,
    condition_aggregates: dict[str, ConditionAggregate] | None = None,
    thresholds: FailureThresholds | None = None,
) -> AttributionOutcome:
    """Pure attribution decision function following the project invariants.

    Decision rules:
      - Missing gold context -> NOT_ATTRIBUTABLE with reason.
      - Provider error in any counterfactual run -> NOT_ATTRIBUTABLE with reason.
      - ORIGINAL passes and NO_CONTEXT passes -> NOT_CONTEXT_DEPENDENT (case does not test RAG).
      - ORIGINAL fails and ORACLE_CONTEXT passes -> RETRIEVAL_CAUSED (retrieval bottleneck).
      - ORIGINAL fails and ORACLE_CONTEXT fails and NO_CONTEXT passes -> PARAMETRIC_KNOWLEDGE.
      - ORIGINAL fails and ORACLE_CONTEXT fails and NO_CONTEXT fails -> GENERATION_CAUSED.
      - ORIGINAL passes and NO_CONTEXT fails -> NOT_ATTRIBUTABLE (not a failure).
    """
    th = thresholds or FailureThresholds()
    errors = condition_errors or {}
    evidence: list[str] = []
    condition_passes = {
        CONDITION_ORIGINAL: original_pass,
        CONDITION_ORACLE_CONTEXT: oracle_pass,
        CONDITION_NO_CONTEXT: no_context_pass,
    }

    condition_pass_rates: dict[str, float] = {}
    condition_scores: dict[str, dict[str, float | None]] = {}
    if condition_aggregates:
        for c_name, agg in condition_aggregates.items():
            condition_pass_rates[c_name] = agg.pass_rate
            condition_scores[c_name] = agg.avg_scores
    else:
        condition_pass_rates = {
            CONDITION_ORIGINAL: 1.0 if original_pass else 0.0,
            CONDITION_ORACLE_CONTEXT: 1.0 if oracle_pass else 0.0,
            CONDITION_NO_CONTEXT: 1.0 if no_context_pass else 0.0,
        }

    # 1. Check for missing gold context
    if not has_gold_context:
        evidence.append("The test case has no gold context (expected_sources or context is empty).")
        return AttributionOutcome(
            verdict=VERDICT_NOT_ATTRIBUTABLE,
            confidence=0.0,
            reason="Missing gold context in test case (expected_sources or context is absent).",
            evidence=evidence,
            condition_passes=condition_passes,
            condition_pass_rates=condition_pass_rates,
            condition_scores=condition_scores,
            repeats=repeats,
            recommendation="Add gold passages or expected sources to the test case to enable counterfactual attribution.",
            signals={"missing_gold_context": True, "thresholds": th.as_dict()},
        )

    # 2. Check for provider error in counterfactual runs
    for cond in (CONDITION_ORACLE_CONTEXT, CONDITION_NO_CONTEXT):
        if errors.get(cond):
            err_msg = errors[cond]
            evidence.append(f"Condition '{cond}' failed with provider error: {err_msg}")
            return AttributionOutcome(
                verdict=VERDICT_NOT_ATTRIBUTABLE,
                confidence=0.0,
                reason=f"Provider error occurred in condition '{cond}': {err_msg}",
                evidence=evidence,
                condition_passes=condition_passes,
                condition_pass_rates=condition_pass_rates,
                condition_scores=condition_scores,
                repeats=repeats,
                recommendation="Resolve provider connectivity or timeout errors before re-running attribution.",
                signals={"condition_error": cond, "error_message": err_msg, "thresholds": th.as_dict()},
            )

    # 3. Calculate confidence based on cleanly executed conditions & repeats (capped at 0.95)
    base_confidence = 0.80 if repeats == 1 else min(0.95, 0.80 + 0.05 * (repeats - 1))
    confidence = round(min(0.95, base_confidence), 2)

    # Evidence details
    oracle_rate = condition_pass_rates.get(CONDITION_ORACLE_CONTEXT, 1.0 if oracle_pass else 0.0)
    no_context_rate = condition_pass_rates.get(CONDITION_NO_CONTEXT, 1.0 if no_context_pass else 0.0)

    if repeats == 1:
        evidence.append("Evaluated with a single trial (N=1); repeat trials (N=3-5) recommended to account for generation noise.")
    else:
        evidence.append(
            f"Evaluated with N={repeats} trials per condition: "
            f"oracle context pass rate {oracle_rate:.0%}, no-context pass rate {no_context_rate:.0%}."
        )

    # 4. Attribution rule logic
    if original_pass:
        if no_context_pass:
            verdict = VERDICT_NOT_CONTEXT_DEPENDENT
            reason = (
                "The model answered correctly even when context was completely removed, "
                "indicating that the question relies on parametric knowledge rather than RAG."
            )
            recommendation = (
                "This test case does not effectively test retrieval. Consider adding cases "
                "that require domain-specific context absent from the model's pre-training data."
            )
            evidence.append("ORIGINAL passed and NO_CONTEXT also passed.")
        else:
            verdict = VERDICT_NOT_ATTRIBUTABLE
            reason = "The original test case passed with retrieved context; counterfactual attribution applies to failures."
            recommendation = "Attribution is intended for failed cases."
            evidence.append("ORIGINAL passed with retrieved context.")
    else:
        # Original failed
        if oracle_pass:
            verdict = VERDICT_RETRIEVAL_CAUSED
            reason = (
                "Retrieval was the bottleneck: the original run failed, but the model succeeded when "
                "provided with the gold context."
            )
            recommendation = (
                "Fix retrieval rather than prompt or model: increase top_k, increase chunk overlap, "
                "or switch to hybrid retrieval with reranking."
            )
            evidence.append(
                f"ORIGINAL failed, but ORACLE_CONTEXT passed (pass rate: {oracle_rate:.0%}). "
                "The model produces correct answers when supporting passages are surfaced."
            )
        elif not oracle_pass and no_context_pass:
            verdict = VERDICT_PARAMETRIC_KNOWLEDGE
            reason = (
                "Context-ignoring behaviour: the model failed with both retrieved and gold context, "
                "but passed when all context was removed."
            )
            recommendation = (
                "The model is distracted or biased by context formatting. Strengthen grounding "
                "system prompts (e.g., 'Answer strictly from the context, quote supporting sentences')."
            )
            evidence.append(
                "ORIGINAL failed and ORACLE_CONTEXT failed, but NO_CONTEXT passed. "
                "The model answers from parametric memory but is derailed by context inputs."
            )
        else:
            verdict = VERDICT_GENERATION_CAUSED
            reason = (
                "Generation bottleneck: the model failed even when supplied with the gold context."
            )
            recommendation = (
                "Tune generation rather than retrieval: clarify the prompt instructions, add few-shot "
                "examples, lower temperature, or upgrade to a more capable model."
            )
            evidence.append(
                f"ORIGINAL failed and ORACLE_CONTEXT also failed (pass rate: {oracle_rate:.0%}). "
                "Retrieving perfect context was not sufficient for the model to answer correctly."
            )

    return AttributionOutcome(
        verdict=verdict,
        confidence=confidence,
        reason=reason,
        evidence=evidence,
        condition_passes=condition_passes,
        condition_pass_rates=condition_pass_rates,
        condition_scores=condition_scores,
        repeats=repeats,
        recommendation=recommendation,
        signals={
            "original_pass": original_pass,
            "oracle_pass": oracle_pass,
            "no_context_pass": no_context_pass,
            "repeats": repeats,
            "thresholds": th.as_dict(),
        },
    )
