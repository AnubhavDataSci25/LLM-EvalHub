"""AI failure diagnosis.

Given a detected failure, produce a structured diagnosis that separates:

  * **observed evidence** — facts taken from the stored result (scores, context,
    answer, configuration),
  * **inferred cause** — what most likely produced the failure,
  * **suggested remediation** — concrete, applicable configuration changes.

Two engines are available and both return the same schema:

  * `heuristic` — deterministic rules over the failure evidence. Always
    available, costs nothing, and is what the improvement loop uses when no
    judge model is configured.
  * `llm` — an LLM reads the same evidence and returns the structured schema.
    Its output is merged with the heuristic suggestions so that every suggestion
    remains machine-applicable.

The engine used is always recorded in `diagnosis_source`, so a reader can tell
which produced a given diagnosis. Nothing here is fabricated: every claim in the
diagnosis is derived from stored evidence.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from langchain_core.prompts import PromptTemplate
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundError, ProviderError
from app.core.logging import get_logger
from app.evaluation.failure_detector import FAILURE_TYPES
from app.models.experiment import EvaluationResult, Experiment, Failure
from app.providers.registry import get_provider
from app.schemas.experiment import DiagnoseRequest

logger = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

DIAGNOSIS_PROMPT = PromptTemplate.from_template(
    """You are diagnosing a failed test case from an LLM evaluation run.

Use ONLY the evidence below. Do not speculate about data you cannot see.

CONFIGURATION
{configuration}

TEST CASE
Question: {question}
Expected answer: {ground_truth}

MODEL OUTPUT
{answer}

RETRIEVED CONTEXT ({context_count} chunk(s))
{context}

MEASURED SCORES
{scores}

RULE-BASED CLASSIFICATION
type={failure_type}, evidence={rule_evidence}

Decide the single most likely root cause and the change most likely to fix it.
Prefer retrieval fixes when the context lacks the answer, and prompt fixes when
the context contains the answer but the model did not use it.

Reply with JSON only:
{{"failure_type": "one of: {allowed_types}",
  "root_cause": "one sentence",
  "confidence": 0.0,
  "evidence": ["facts you observed above"],
  "suggestions": [{{"action": "increase_top_k | increase_chunk_overlap | reduce_chunk_size | change_retriever | strengthen_grounding_prompt | clarify_prompt | reduce_context | switch_model | lower_temperature | add_citation_requirement | none",
                    "detail": "what to change and why",
                    "parameter": "top_k|chunk_overlap|chunk_size|retriever|system_prompt|temperature|model|none",
                    "value": "suggested new value or null"}}],
  "expected_improvement": "which metric should move and in which direction"}}"""
)

#: Machine-applicable remediation catalogue. `apply` values feed straight into
#: the improvement loop's experiment overrides.
REMEDIATIONS: dict[str, list[dict[str, Any]]] = {
    "poor_retrieval": [
        {
            "action": "increase_top_k",
            "parameter": "top_k",
            "detail": "Retrieve more candidate chunks so the supporting passage has a chance to appear.",
            "expected_improvement": "context_recall should rise; watch context_precision for dilution.",
        },
        {
            "action": "increase_chunk_overlap",
            "parameter": "chunk_overlap",
            "detail": "Larger overlap stops answers being split across a chunk boundary.",
            "expected_improvement": "context_recall should rise on boundary-spanning answers.",
        },
        {
            "action": "change_retriever",
            "parameter": "retriever",
            "detail": "Hybrid retrieval combines keyword and vector ranking, which helps when questions reuse document wording.",
            "expected_improvement": "context_precision and context_recall should both improve.",
        },
    ],
    "unsupported_claim": [
        {
            "action": "strengthen_grounding_prompt",
            "parameter": "system_prompt",
            "detail": "Instruct the model to answer only from context and to state explicitly when the context is insufficient.",
            "expected_improvement": "faithfulness should rise, possibly at the cost of answer coverage.",
        },
        {
            "action": "add_citation_requirement",
            "parameter": "system_prompt",
            "detail": "Require the model to quote the supporting sentence, which makes ungrounded claims visible.",
            "expected_improvement": "faithfulness should rise and unsupported claims become auditable.",
        },
    ],
    "hallucination": [
        {
            "action": "strengthen_grounding_prompt",
            "parameter": "system_prompt",
            "detail": "Add an explicit refusal instruction so the model stops filling gaps from parametric memory.",
            "expected_improvement": "faithfulness and correctness should both rise.",
        },
        {
            "action": "lower_temperature",
            "parameter": "temperature",
            "detail": "A non-zero temperature increases invented specifics on factual tasks.",
            "expected_improvement": "fewer fabricated details across repeated runs.",
        },
        {
            "action": "switch_model",
            "parameter": "model",
            "detail": "If grounding instructions do not help, the model may not follow them reliably on this task.",
            "expected_improvement": "compare faithfulness across models before committing.",
        },
    ],
    "incorrect_answer": [
        {
            "action": "clarify_prompt",
            "parameter": "system_prompt",
            "detail": "State the expected answer format and required precision so partial answers are not produced.",
            "expected_improvement": "correctness should rise.",
        },
        {
            "action": "switch_model",
            "parameter": "model",
            "detail": "Benchmark a stronger model on the same dataset before concluding the prompt is at fault.",
            "expected_improvement": "correctness comparison across models.",
        },
    ],
    "missing_information": [
        {
            "action": "clarify_prompt",
            "parameter": "system_prompt",
            "detail": "Ask for the complete answer including every qualifying condition, not just the headline value.",
            "expected_improvement": "correctness should rise as coverage of the expected answer improves.",
        },
        {
            "action": "increase_top_k",
            "parameter": "top_k",
            "detail": "The missing part of the answer may live in a chunk that was ranked just outside top_k.",
            "expected_improvement": "context_recall and correctness should rise together.",
        },
    ],
    "low_relevance": [
        {
            "action": "clarify_prompt",
            "parameter": "system_prompt",
            "detail": "Instruct the model to answer the question directly first, then add context if needed.",
            "expected_improvement": "answer_relevance should rise.",
        },
        {
            "action": "reduce_context",
            "parameter": "top_k",
            "detail": "Too much context can pull the answer off-topic; try a smaller top_k.",
            "expected_improvement": "answer_relevance up, context_recall down — check both.",
        },
    ],
    "empty_response": [
        {
            "action": "clarify_prompt",
            "parameter": "system_prompt",
            "detail": "Some models return nothing when a refusal instruction is too strict; soften it to require a stated refusal sentence.",
            "expected_improvement": "empty responses should disappear.",
        },
        {
            "action": "switch_model",
            "parameter": "model",
            "detail": "Persistent empty output usually indicates a model/route problem rather than a prompt problem.",
            "expected_improvement": "non-empty completions.",
        },
    ],
    "timeout": [
        {
            "action": "switch_model",
            "parameter": "model",
            "detail": "Choose a lower-latency model, or raise REQUEST_TIMEOUT_SECONDS if the slower model is acceptable.",
            "expected_improvement": "fewer timeout errors; latency should drop.",
        },
        {
            "action": "reduce_context",
            "parameter": "top_k",
            "detail": "Long prompts increase time-to-first-token; a smaller top_k shortens the request.",
            "expected_improvement": "latency should drop.",
        },
    ],
    "provider_error": [
        {
            "action": "none",
            "parameter": "none",
            "detail": "This is an infrastructure failure, not a quality failure. Check credentials, quota and provider status, then re-run.",
            "expected_improvement": "the case should complete once the provider call succeeds.",
        }
    ],
    "high_latency": [
        {
            "action": "switch_model",
            "parameter": "model",
            "detail": "Answer quality was acceptable, so the trade-off to examine is a faster model at similar quality.",
            "expected_improvement": "latency down; verify correctness does not regress.",
        },
        {
            "action": "reduce_context",
            "parameter": "top_k",
            "detail": "Fewer retrieved chunks means a shorter prompt and lower latency.",
            "expected_improvement": "latency down; watch context_recall.",
        },
    ],
}

GROUNDING_PROMPT_SUGGESTION = (
    "You are answering strictly from the provided context. Every claim you make must be "
    "supported by a sentence in the context. If the context does not contain the answer, "
    "reply exactly: 'The provided context does not contain this information.' "
    "Do not use outside knowledge."
)

CITATION_PROMPT_SUGGESTION = (
    "Answer from the context only. After your answer, quote the exact sentence from the "
    "context that supports it, prefixed with 'Source: '. If no sentence supports the "
    "answer, say the context is insufficient instead of answering."
)

CLARITY_PROMPT_SUGGESTION = (
    "Answer the question directly in the first sentence. Include every qualifying "
    "condition, number and time limit exactly as written in the context. Do not add "
    "background the question did not ask for."
)


def _suggestion_value(action: str, experiment: Experiment | None) -> Any:
    """Turn a remediation action into a concrete, applicable value."""
    top_k = experiment.top_k if experiment else 4
    overlap = experiment.chunk_overlap if experiment else 120
    chunk = experiment.chunk_size if experiment else 800
    return {
        "increase_top_k": min(20, top_k + 2),
        "reduce_context": max(1, top_k - 1),
        "increase_chunk_overlap": min(chunk // 2, overlap + 100),
        "reduce_chunk_size": max(200, chunk - 200),
        "change_retriever": "hybrid" if (experiment and experiment.retriever != "hybrid") else "vector",
        "strengthen_grounding_prompt": GROUNDING_PROMPT_SUGGESTION,
        "add_citation_requirement": CITATION_PROMPT_SUGGESTION,
        "clarify_prompt": CLARITY_PROMPT_SUGGESTION,
        "lower_temperature": 0.0,
        "switch_model": None,
        "none": None,
    }.get(action)


def _applicable(action: str, parameter: str, value: Any, experiment: Experiment | None) -> dict[str, Any]:
    """Build the override payload the improvement loop can apply directly."""
    if parameter in {"none", "model"} or value is None:
        return {}
    if parameter == "retriever" and experiment and not experiment.rag_enabled:
        return {}
    if parameter in {"top_k", "chunk_overlap", "chunk_size"} and experiment and not experiment.rag_enabled:
        return {}
    return {parameter: value}


class DiagnosisService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- reads -------------------------------------------------------------
    def get_failure(self, failure_id: str) -> Failure:
        failure = self.db.execute(
            select(Failure).where(Failure.id == failure_id).options(
                selectinload(Failure.result).selectinload(EvaluationResult.metrics),
                selectinload(Failure.attribution),
            )
        ).scalar_one_or_none()
        if failure is None:
            raise NotFoundError(f"Failure '{failure_id}' was not found.")
        return failure

    def list_failures(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        run_id: str | None = None,
        experiment_id: str | None = None,
        failure_type: str | None = None,
        severity: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        diagnosed: bool | None = None,
    ) -> tuple[list[Failure], int]:
        stmt = select(Failure).options(
            selectinload(Failure.result).selectinload(EvaluationResult.metrics),
            selectinload(Failure.attribution),
        )
        if run_id:
            stmt = stmt.where(Failure.run_id == run_id)
        if experiment_id:
            stmt = stmt.where(Failure.experiment_id == experiment_id)
        if failure_type:
            stmt = stmt.where(Failure.failure_type == failure_type)
        if severity:
            stmt = stmt.where(Failure.severity == severity)
        if diagnosed is True:
            stmt = stmt.where(Failure.diagnosis.is_not(None))
        if diagnosed is False:
            stmt = stmt.where(Failure.diagnosis.is_(None))
        if provider or model:
            stmt = stmt.join(EvaluationResult, Failure.result_id == EvaluationResult.id)
            if provider:
                stmt = stmt.where(EvaluationResult.provider == provider)
            if model:
                stmt = stmt.where(EvaluationResult.model == model)
        total = int(
            self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        )
        stmt = stmt.order_by(Failure.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().unique().all()), total

    def distribution(self, run_id: str | None = None) -> list[dict[str, Any]]:
        stmt = select(Failure.failure_type, func.count(Failure.id)).group_by(Failure.failure_type)
        if run_id:
            stmt = stmt.where(Failure.run_id == run_id)
        rows = self.db.execute(stmt).all()
        return [
            {
                "failure_type": failure_type,
                "label": failure_type.replace("_", " ").title(),
                "description": FAILURE_TYPES.get(failure_type, ""),
                "count": int(count),
            }
            for failure_type, count in sorted(rows, key=lambda r: -r[1])
        ]

    # -- diagnosis ---------------------------------------------------------
    async def diagnose(self, failure_id: str, payload: DiagnoseRequest) -> Failure:
        failure = self.get_failure(failure_id)
        if failure.diagnosis and not payload.force:
            return failure

        result = failure.result
        experiment = self.db.get(Experiment, failure.experiment_id)
        heuristic = self.build_heuristic(failure, result, experiment)

        provider_key = payload.provider or (experiment.judge_provider if experiment else None)
        model_id = payload.model or (experiment.judge_model if experiment else None)

        diagnosis = heuristic
        source = "heuristic"
        if provider_key and model_id:
            llm_diagnosis = await self._llm_diagnose(
                failure, result, experiment, provider_key, model_id
            )
            if llm_diagnosis:
                diagnosis = self._merge(heuristic, llm_diagnosis)
                source = "llm"

        failure.diagnosis = diagnosis
        failure.diagnosis_source = source
        failure.diagnosed_at = datetime.now(UTC)
        self.db.flush()
        return failure

    # -- heuristic engine ---------------------------------------------------
    def build_heuristic(
        self,
        failure: Failure,
        result: EvaluationResult | None,
        experiment: Experiment | None,
    ) -> dict[str, Any]:
        failure_type = failure.failure_type
        scores = (failure.signals or {}).get("scores", {})
        contexts = list(result.retrieved_context or []) if result else []

        evidence = list(failure.evidence or [])
        if result and not result.generated_answer:
            evidence.append("The stored answer is empty.")
        if failure_type == "poor_retrieval":
            evidence.append(
                f"{len(contexts)} chunk(s) were retrieved with top_k="
                f"{experiment.top_k if experiment else 'n/a'}."
            )
        if result and result.error_kind:
            evidence.append(f"Provider reported '{result.error_kind}'.")

        # Check if an empirical counterfactual attribution exists for this failure
        from app.models.attribution import AttributionRun

        attribution = getattr(failure, "attribution", None)
        if attribution is None:
            attribution = self.db.execute(
                select(AttributionRun)
                .where(AttributionRun.failure_id == failure.id)
                .order_by(AttributionRun.created_at.desc())
            ).scalars().first()

        confirmed_by_attribution = False
        attribution_verdict = None

        if attribution and attribution.verdict != "NOT_ATTRIBUTABLE":
            confirmed_by_attribution = True
            attribution_verdict = attribution.verdict
            evidence.insert(
                0,
                f"Empirical counterfactual test confirmed {attribution.verdict} "
                f"(confidence {attribution.confidence:.2f}): {attribution.reason}",
            )

            if attribution.verdict == "RETRIEVAL_CAUSED":
                failure_type = "poor_retrieval"
                root_cause = (
                    "Confirmed by counterfactual test: retrieval was the bottleneck. "
                    "The model answered accurately when supplied with the gold context."
                )
            elif attribution.verdict == "GENERATION_CAUSED":
                failure_type = "incorrect_answer"
                root_cause = (
                    "Confirmed by counterfactual test: generation failure. "
                    "The model failed even when supplied with the gold context."
                )
            elif attribution.verdict == "PARAMETRIC_KNOWLEDGE":
                failure_type = "hallucination"
                root_cause = (
                    "Confirmed by counterfactual test: context-ignoring model. "
                    "The model answers from parametric memory rather than grounding in provided context."
                )
            else:
                root_cause = attribution.reason
        else:
            root_cause = {
                "poor_retrieval": "The retriever did not return the passage containing the answer, so the model could not have answered correctly regardless of its capability.",
                "unsupported_claim": "The answer contains at least one claim that the retrieved context does not support.",
                "hallucination": "The model produced specific content that is both absent from the context and inconsistent with the expected answer.",
                "incorrect_answer": "The model answered confidently but disagreed with the expected answer.",
                "missing_information": "The answer is directionally right but omits part of the expected answer.",
                "low_relevance": "The response did not address the question that was asked.",
                "empty_response": "The provider returned a successful response containing no text.",
                "timeout": "The provider did not respond within the configured timeout.",
                "provider_error": "The request failed at the provider before any answer was generated.",
                "high_latency": "Answer quality was acceptable but the response exceeded the latency budget.",
            }.get(failure_type, "The measured scores fell below the configured thresholds.")

        suggestions = []
        for template in REMEDIATIONS.get(failure_type, []):
            value = _suggestion_value(template["action"], experiment)
            suggestions.append(
                {
                    "action": template["action"],
                    "parameter": template["parameter"],
                    "detail": template["detail"],
                    "value": value,
                    "expected_improvement": template["expected_improvement"],
                    "apply": _applicable(
                        template["action"], template["parameter"], value, experiment
                    ),
                }
            )
        suggestions = [s for s in suggestions if s["apply"] or s["parameter"] in {"none", "model"}]

        return {
            "failure_type": failure_type,
            "failure_label": (
                f"{failure_type.replace('_', ' ').title()} (Confirmed by counterfactual)"
                if confirmed_by_attribution
                else failure_type.replace("_", " ").title()
            ),
            "root_cause": root_cause,
            "confidence": round(min(0.95, float(attribution.confidence if confirmed_by_attribution else failure.confidence)), 2),
            "evidence": evidence[:8],
            "observed_scores": scores,
            "suggestions": suggestions,
            "expected_improvement": (
                suggestions[0]["expected_improvement"] if suggestions else "No automatic remediation available."
            ),
            "engine": "counterfactual" if confirmed_by_attribution else "heuristic",
            "attribution_confirmed": confirmed_by_attribution,
            "attribution_verdict": attribution_verdict,
        }

    # -- LLM engine ---------------------------------------------------------
    async def _llm_diagnose(
        self,
        failure: Failure,
        result: EvaluationResult | None,
        experiment: Experiment | None,
        provider_key: str,
        model_id: str,
    ) -> dict[str, Any] | None:
        provider = get_provider(provider_key)
        if not provider.is_configured:
            logger.info("diagnosis provider %s not configured; heuristic only", provider_key)
            return None

        contexts = list(result.retrieved_context or []) if result else []
        configuration = json.dumps(
            {
                "provider": result.provider if result else None,
                "model": result.model if result else None,
                "prompt_label": experiment.prompt_label if experiment else None,
                "temperature": experiment.temperature if experiment else None,
                "rag_enabled": experiment.rag_enabled if experiment else None,
                "retriever": experiment.retriever if experiment else None,
                "top_k": experiment.top_k if experiment else None,
                "chunk_size": experiment.chunk_size if experiment else None,
                "chunk_overlap": experiment.chunk_overlap if experiment else None,
            },
            indent=2,
        )
        prompt = DIAGNOSIS_PROMPT.format(
            configuration=configuration,
            question=(result.question if result else "")[:1500],
            ground_truth=(result.ground_truth if result else None) or "(none supplied)",
            answer=(result.generated_answer if result else None) or "(empty)",
            context_count=len(contexts),
            context="\n---\n".join(c[:900] for c in contexts[:5]) or "(no context retrieved)",
            scores=json.dumps((failure.signals or {}).get("scores", {}), indent=2),
            failure_type=failure.failure_type,
            rule_evidence="; ".join(failure.evidence or [])[:800],
            allowed_types=", ".join(FAILURE_TYPES),
        )

        try:
            response = await provider.generate(
                prompt=prompt,
                model=model_id,
                temperature=0.0,
                max_tokens=700,
                system_prompt=(
                    "You are a senior LLM evaluation engineer. You reason only from the "
                    "evidence given and reply with JSON only."
                ),
            )
        except ProviderError as exc:
            logger.warning("diagnosis LLM call failed: %s", exc.message)
            return None

        text = (response.text or "").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        payload: dict[str, Any] | None = None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = _JSON_BLOCK.search(text)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except json.JSONDecodeError:
                    payload = None
        if not isinstance(payload, dict):
            logger.warning("diagnosis LLM returned unparseable output")
            return None
        payload["engine"] = "llm"
        payload["judge_model"] = f"{provider_key}/{model_id}"
        return payload

    # -- merging -----------------------------------------------------------
    @staticmethod
    def _merge(heuristic: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
        """Keep the LLM's reasoning, keep the heuristic's applicable actions.

        The LLM is better at explaining *why*; the heuristic guarantees every
        suggestion maps to a real configuration change the improvement loop can
        apply. Merging keeps both properties.
        """
        merged = dict(heuristic)
        failure_type = llm.get("failure_type")
        if failure_type in FAILURE_TYPES:
            merged["failure_type"] = failure_type
            merged["failure_label"] = failure_type.replace("_", " ").title()
        if llm.get("root_cause"):
            merged["root_cause"] = str(llm["root_cause"])[:600]
        try:
            merged["confidence"] = round(max(0.0, min(1.0, float(llm.get("confidence", 0)))), 2)
        except (TypeError, ValueError):
            pass
        llm_evidence = [str(e)[:300] for e in (llm.get("evidence") or []) if e]
        merged["evidence"] = list(dict.fromkeys([*llm_evidence, *heuristic.get("evidence", [])]))[:8]
        if llm.get("expected_improvement"):
            merged["expected_improvement"] = str(llm["expected_improvement"])[:400]

        # Re-order heuristic suggestions to match the LLM's preferred action.
        preferred = [
            str(s.get("action"))
            for s in (llm.get("suggestions") or [])
            if isinstance(s, dict) and s.get("action")
        ]
        if preferred:
            ordered = sorted(
                merged.get("suggestions", []),
                key=lambda s: preferred.index(s["action"]) if s["action"] in preferred else 99,
            )
            merged["suggestions"] = ordered
            llm_details = {
                str(s.get("action")): str(s.get("detail", ""))[:400]
                for s in (llm.get("suggestions") or [])
                if isinstance(s, dict)
            }
            for suggestion in merged["suggestions"]:
                if suggestion["action"] in llm_details and llm_details[suggestion["action"]]:
                    suggestion["llm_detail"] = llm_details[suggestion["action"]]
        merged["engine"] = "llm+heuristic"
        merged["judge_model"] = llm.get("judge_model")
        return merged
