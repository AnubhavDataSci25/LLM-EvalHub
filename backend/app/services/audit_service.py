"""Model availability audit and live probe service.

Discovers candidates via live provider listing endpoints, filters out non-chat models,
executes bounded verification probes, classifies statuses with machine-readable reasons,
caches results with TTL, and invalidates stale entries.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ProviderError, RateLimitedError, ValidationFailedError
from app.core.logging import get_logger
from app.db.base import new_id
from app.models.audit import AuditRun, ModelAvailability
from app.providers.base import LLMProvider
from app.providers.catalog import static_models
from app.providers.filtering import filter_chat_models
from app.providers.registry import (
    all_providers,
    get_provider,
    is_provider_registered,
)

logger = get_logger(__name__)

VALID_STATUSES = {
    "AVAILABLE",
    "RATE_LIMITED",
    "NOT_ENTITLED",
    "NOT_FOUND",
    "INVALID_CREDENTIALS",
    "TIMEOUT",
    "UPSTREAM_ERROR",
    "EMPTY_RESPONSE",
    "NOT_PROBED",
}


def _now() -> datetime:
    return datetime.now(UTC)


class AuditService:
    """Orchestrates live model discovery, verification probes, caching and auditing."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- Cache Helpers --------------------------------------------------------

    def is_fresh(self, checked_at: datetime | None) -> bool:
        if not checked_at:
            return False
        # Normalize to UTC
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        age_hours = (_now() - checked_at).total_seconds() / 3600.0
        return age_hours < float(settings.model_audit_ttl_hours)

    def is_record_fresh(self, rec: ModelAvailability) -> bool:
        return self.is_fresh(rec.checked_at)

    def get_latest_availability(self, provider: str, model_id: str) -> ModelAvailability | None:
        return (
            self.db.execute(
                select(ModelAvailability)
                .where(
                    ModelAvailability.provider == provider,
                    ModelAvailability.model_id == model_id,
                )
                .order_by(desc(ModelAvailability.checked_at))
                .limit(1)
            )
            .scalars()
            .first()
        )

    def get_latest_for_model(self, provider: str, model_id: str) -> ModelAvailability | None:
        return self.get_latest_availability(provider, model_id)

    def get_all_latest(self) -> list[ModelAvailability]:
        """Fetch the most recent availability entry for every (provider, model_id) pair."""
        records = (
            self.db.execute(
                select(ModelAvailability).order_by(
                    ModelAvailability.provider,
                    ModelAvailability.model_id,
                    desc(ModelAvailability.checked_at),
                )
            )
            .scalars()
            .all()
        )
        seen: set[tuple[str, str]] = set()
        latest: list[ModelAvailability] = []
        for rec in records:
            key = (rec.provider, rec.model_id)
            if key not in seen:
                seen.add(key)
                latest.append(rec)
        return latest

    # -- Single Model Probing -------------------------------------------------

    async def probe_model(
        self, provider: LLMProvider, model_id: str
    ) -> tuple[str, str, float | None, float | None]:
        """Run a minimal, cheap probe on a model.

        Returns (status, reason, latency_ms, retry_after).
        """
        started = time.perf_counter()
        try:
            response = await provider.generate(
                prompt="Say 1",
                model=model_id,
                temperature=0.0,
                max_tokens=8,
                timeout=float(settings.probe_timeout_seconds),
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            if response.is_empty:
                return "EMPTY_RESPONSE", "Probe returned empty completion.", latency_ms, None
            return "AVAILABLE", "Probe succeeded with non-empty response.", latency_ms, None

        except RateLimitedError as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return (
                "RATE_LIMITED",
                f"Rate limited (429): {exc.message}",
                latency_ms,
                exc.retry_after,
            )

        except ProviderError as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            msg = exc.message or ""
            status_code = exc.status or 0
            kind = exc.kind or ""

            if kind == "invalid_credentials" or status_code == 401:
                return (
                    "INVALID_CREDENTIALS",
                    f"Authentication failed (401): {msg}",
                    latency_ms,
                    None,
                )

            if kind == "model_unavailable" or status_code == 404:
                return (
                    "NOT_FOUND",
                    f"Model not found or retired (404): {msg}",
                    latency_ms,
                    None,
                )

            # Entitlement / Tier checks (402, 403, or payment/tier keywords)
            lower_msg = msg.lower()
            is_entitlement = (
                kind in ("quota_exhausted", "not_entitled")
                or status_code in (402, 403)
                or any(
                    w in lower_msg
                    for w in (
                        "tier",
                        "plan",
                        "enterprise",
                        "paid",
                        "payment",
                        "credit",
                        "billing",
                        "restricted",
                        "permission denied",
                    )
                )
            )
            if is_entitlement:
                return (
                    "NOT_ENTITLED",
                    f"Tier/plan restricted: {msg}",
                    latency_ms,
                    None,
                )

            if kind == "timeout":
                return "TIMEOUT", f"Probe timed out: {msg}", latency_ms, None

            if kind == "upstream_error" or status_code >= 500:
                return "UPSTREAM_ERROR", f"Upstream error ({status_code}): {msg}", latency_ms, None

            return "NOT_FOUND", f"Probe rejected: {msg}", latency_ms, None

        except TimeoutError:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return "TIMEOUT", "Probe timed out.", latency_ms, None

        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return "UPSTREAM_ERROR", f"Unexpected error during probe: {str(exc)[:200]}", latency_ms, None

    async def recheck_model(self, provider_key: str, model_id: str) -> ModelAvailability:
        """On-demand live probe for a single model, updating cache and history."""
        provider = get_provider(provider_key)
        if not provider.is_configured:
            status, reason = "INVALID_CREDENTIALS", "Provider credentials not configured."
            latency_ms, retry_after = None, None
        else:
            status, reason, latency_ms, retry_after = await self.probe_model(provider, model_id)

        rec = ModelAvailability(
            id=new_id("mav"),
            provider=provider_key,
            model_id=model_id,
            status=status,
            reason=reason,
            checked_at=_now(),
            latency_ms=round(latency_ms, 2) if latency_ms else None,
            retry_after=retry_after,
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        logger.info("rechecked model %s/%s -> %s (%s)", provider_key, model_id, status, reason)
        return rec

    def record_evaluation_failure(
        self,
        provider_key: str,
        model_id: str,
        error: ProviderError | str,
        message: str | None = None,
    ) -> None:
        """Automatically invalidates or updates a model's cache when an evaluation run fails."""
        if isinstance(error, ProviderError):
            kind = error.kind or ""
            status_code = error.status or 0
            msg = error.message or ""
        else:
            kind = str(error)
            status_code = 0
            msg = message or str(error)

        if kind == "model_unavailable" or status_code == 404:
            status = "NOT_FOUND"
        elif kind == "invalid_credentials" or status_code == 401:
            status = "INVALID_CREDENTIALS"
        elif kind in ("quota_exhausted", "not_entitled") or status_code in (402, 403):
            status = "NOT_ENTITLED"
        elif kind == "rate_limited" or status_code == 429:
            status = "RATE_LIMITED"
        else:
            return

        rec = ModelAvailability(
            id=new_id("mav"),
            provider=provider_key,
            model_id=model_id,
            status=status,
            reason=f"Evaluation failed: {msg}",
            checked_at=_now(),
        )
        self.db.add(rec)
        self.db.commit()
        logger.info("auto-invalidated model %s/%s after run failure: %s", provider_key, model_id, status)

    # -- Dry Run Estimation ---------------------------------------------------

    async def estimate_audit_calls(
        self,
        provider_keys_to_audit: list[str] | None = None,
        max_probes_per_provider: int = 15,
        providers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Estimate the number of probe calls without making any generation requests."""
        target_keys = providers if providers is not None else (provider_keys_to_audit or [])
        by_provider: dict[str, int] = {}
        candidate_counts: dict[str, int] = {}
        total = 0

        for key in target_keys:
            if not is_provider_registered(key):
                continue
            provider = get_provider(key)
            if not provider.is_configured:
                candidate_counts[key] = 0
                by_provider[key] = 0
                continue
            try:
                candidates = await provider.discover_models()
            except Exception:
                candidates = static_models(key)

            chat_candidates, _ = filter_chat_models(candidates)
            c_count = len(chat_candidates)
            candidate_counts[key] = c_count
            est = min(c_count, max_probes_per_provider)
            by_provider[key] = est
            total += est

        return {
            "dry_run": True,
            "estimated_calls": total,
            "estimated_probes": total,
            "providers_targeted": list(by_provider.keys()),
            "by_provider": by_provider,
            "candidate_counts": candidate_counts,
            "warnings": [],
        }

    # -- Full Provider Audit --------------------------------------------------

    async def execute_audit(
        self,
        audit_run_id: str | None = None,
        target_providers: list[str] | None = None,
        max_probes_per_provider: int = 15,
        providers: list[str] | None = None,
    ) -> AuditRun:
        """Execute a full live audit run across requested providers."""
        target_keys = providers if providers is not None else target_providers
        if audit_run_id is None:
            audit_run = AuditRun(
                id=new_id("aud"),
                status="running",
                providers=target_keys or [p.key for p in all_providers()],
                dry_run=False,
            )
            self.db.add(audit_run)
            self.db.commit()
        else:
            audit_run = self.db.get(AuditRun, audit_run_id)
            if not audit_run:
                raise ValidationFailedError(f"AuditRun '{audit_run_id}' not found.")

        keys = target_keys or [p.key for p in all_providers()]
        # Filter to registered providers, skipping mock unless enabled
        keys = [k for k in keys if is_provider_registered(k)]
        if not settings.enable_mock_provider and "mock" in keys:
            keys.remove("mock")

        audit_run.providers = keys
        audit_run.status = "running"
        self.db.commit()

        overall_summary: dict[str, Any] = {
            "total_candidates": 0,
            "total_probed": 0,
            "by_status": {},
            "by_provider": {},
        }
        semaphore = asyncio.Semaphore(settings.max_probe_concurrency)

        try:
            for p_key in keys:
                provider = get_provider(p_key)
                p_summary: dict[str, int] = {}

                # 1. Check credentials
                if not provider.is_configured:
                    fallback = static_models(p_key)
                    for m in fallback:
                        rec = ModelAvailability(
                            id=new_id("mav"),
                            provider=p_key,
                            model_id=m.id,
                            status="INVALID_CREDENTIALS",
                            reason=f"Provider '{p_key}' credentials not configured.",
                            checked_at=_now(),
                            audit_run_id=audit_run.id,
                            context_window=m.context_window,
                        )
                        self.db.add(rec)
                        p_summary["INVALID_CREDENTIALS"] = p_summary.get("INVALID_CREDENTIALS", 0) + 1
                    overall_summary["by_provider"][p_key] = p_summary
                    continue

                # 2. Live model discovery
                try:
                    candidates = await provider.discover_models()
                except Exception as exc:
                    logger.warning("Discovery error for %s: %s; falling back to static", p_key, exc)
                    candidates = static_models(p_key)

                chat_candidates, excluded = filter_chat_models(candidates)
                overall_summary["total_candidates"] += len(chat_candidates)

                quota_exhausted = False
                auth_failed = False
                probes_run = 0

                for idx, candidate in enumerate(chat_candidates):
                    # Probe cap enforcement
                    if idx >= max_probes_per_provider:
                        rec = ModelAvailability(
                            id=new_id("mav"),
                            provider=p_key,
                            model_id=candidate.id,
                            status="NOT_PROBED",
                            reason=f"Cap reached (max {max_probes_per_provider} probes per provider).",
                            checked_at=_now(),
                            audit_run_id=audit_run.id,
                            context_window=candidate.context_window,
                            tier=candidate.tier,
                        )
                        self.db.add(rec)
                        p_summary["NOT_PROBED"] = p_summary.get("NOT_PROBED", 0) + 1
                        continue

                    if auth_failed:
                        rec = ModelAvailability(
                            id=new_id("mav"),
                            provider=p_key,
                            model_id=candidate.id,
                            status="NOT_PROBED",
                            reason="Skipped: provider credentials invalid.",
                            checked_at=_now(),
                            audit_run_id=audit_run.id,
                            context_window=candidate.context_window,
                            tier=candidate.tier,
                        )
                        self.db.add(rec)
                        p_summary["NOT_PROBED"] = p_summary.get("NOT_PROBED", 0) + 1
                        continue

                    if quota_exhausted:
                        rec = ModelAvailability(
                            id=new_id("mav"),
                            provider=p_key,
                            model_id=candidate.id,
                            status="NOT_PROBED",
                            reason="Skipped: provider quota exhausted.",
                            checked_at=_now(),
                            audit_run_id=audit_run.id,
                            context_window=candidate.context_window,
                            tier=candidate.tier,
                        )
                        self.db.add(rec)
                        p_summary["NOT_PROBED"] = p_summary.get("NOT_PROBED", 0) + 1
                        continue

                    # Execute cheap probe with concurrency control
                    async with semaphore:
                        status, reason, latency_ms, retry_after = await self.probe_model(
                            provider, candidate.id
                        )

                    probes_run += 1
                    overall_summary["total_probed"] += 1
                    p_summary[status] = p_summary.get(status, 0) + 1

                    if status == "INVALID_CREDENTIALS":
                        auth_failed = True
                    elif status == "RATE_LIMITED":
                        # If retry-after is large or message says quota exhausted, early-stop probing this provider
                        if (retry_after and retry_after > 60) or "quota" in reason.lower():
                            quota_exhausted = True

                    rec = ModelAvailability(
                        id=new_id("mav"),
                        provider=p_key,
                        model_id=candidate.id,
                        status=status,
                        reason=reason,
                        checked_at=_now(),
                        latency_ms=round(latency_ms, 2) if latency_ms else None,
                        retry_after=retry_after,
                        audit_run_id=audit_run.id,
                        context_window=candidate.context_window,
                        tier=candidate.tier,
                    )
                    self.db.add(rec)

                overall_summary["by_provider"][p_key] = p_summary

            # Aggregate by status
            for p_counts in overall_summary["by_provider"].values():
                for stat, cnt in p_counts.items():
                    overall_summary["by_status"][stat] = overall_summary["by_status"].get(stat, 0) + cnt

            audit_run.summary = overall_summary
            audit_run.status = "COMPLETED"
            audit_run.completed_at = _now()
            self.db.commit()
            logger.info("audit run %s completed: %s", audit_run.id, overall_summary)
            return audit_run

        except Exception as exc:
            self.db.rollback()
            audit_run = self.db.get(AuditRun, audit_run_id)
            if audit_run:
                audit_run.status = "failed"
                audit_run.error = str(exc)
                audit_run.completed_at = _now()
                self.db.commit()
            logger.exception("audit run %s failed", audit_run_id)
            raise

    # -- Read Models for Selection --------------------------------------------

    def get_available_models_grouped(
        self, include_limited: bool = False, include_unavailable: bool = False
    ) -> dict[str, list[dict[str, Any]]]:
        """Return available models grouped by provider.

        Invariant: Returns ONLY AVAILABLE models by default.
        Never marks a model AVAILABLE without live confirmation.
        """
        latest_records = self.get_all_latest()
        latest_map = {(r.provider, r.model_id): r for r in latest_records}

        out: dict[str, list[dict[str, Any]]] = {}

        for provider in all_providers():
            p_key = provider.key
            if not settings.enable_mock_provider and p_key == "mock":
                continue

            models_for_p: list[dict[str, Any]] = []

            # If provider is not configured, do not show available models
            if not provider.is_configured and not include_unavailable:
                out[p_key] = []
                continue

            # Check cached availability records for this provider
            p_records = [r for (p, _), r in latest_map.items() if p == p_key]

            for rec in p_records:
                is_fresh = self.is_fresh(rec.checked_at)

                if rec.status == "AVAILABLE":
                    if not is_fresh and not include_unavailable:
                        continue  # Stale, requires re-check
                    models_for_p.append(
                        {
                            "id": rec.model_id,
                            "provider": p_key,
                            "label": rec.model_id,
                            "status": rec.status,
                            "reason": rec.reason,
                            "last_checked_at": rec.checked_at.isoformat(),
                            "latency_ms": rec.latency_ms,
                            "retry_after": rec.retry_after,
                            "context_window": rec.context_window,
                            "tier": rec.tier,
                            "is_stale": not is_fresh,
                        }
                    )
                elif rec.status == "RATE_LIMITED" and (include_limited or include_unavailable):
                    models_for_p.append(
                        {
                            "id": rec.model_id,
                            "provider": p_key,
                            "label": rec.model_id,
                            "status": rec.status,
                            "reason": rec.reason,
                            "last_checked_at": rec.checked_at.isoformat(),
                            "latency_ms": rec.latency_ms,
                            "retry_after": rec.retry_after,
                            "context_window": rec.context_window,
                            "tier": rec.tier,
                            "is_stale": not is_fresh,
                        }
                    )
                elif include_unavailable:
                    models_for_p.append(
                        {
                            "id": rec.model_id,
                            "provider": p_key,
                            "label": rec.model_id,
                            "status": rec.status,
                            "reason": rec.reason,
                            "last_checked_at": rec.checked_at.isoformat(),
                            "latency_ms": rec.latency_ms,
                            "retry_after": rec.retry_after,
                            "context_window": rec.context_window,
                            "tier": rec.tier,
                            "is_stale": not is_fresh,
                        }
                    )

            out[p_key] = models_for_p

        return out

    # -- Status Summary -------------------------------------------------------

    def get_provider_status_summaries(self) -> list[dict[str, Any]]:
        """Summarise per provider: key configured, listing reachable, counts per status, last audit time."""
        latest_records = self.get_all_latest()
        summaries: list[dict[str, Any]] = []

        for provider in all_providers():
            p_key = provider.key
            if not settings.enable_mock_provider and p_key == "mock":
                continue

            p_recs = [r for r in latest_records if r.provider == p_key]
            counts = dict.fromkeys(VALID_STATUSES, 0)
            last_checked: datetime | None = None

            for r in p_recs:
                if r.status in counts:
                    counts[r.status] += 1
                if last_checked is None or r.checked_at > last_checked:
                    last_checked = r.checked_at

            summaries.append(
                {
                    "provider": p_key,
                    "display_name": provider.display_name,
                    "configured": provider.is_configured,
                    "listing_reachable": provider.is_configured,
                    "counts": counts,
                    "last_audit_at": last_checked.isoformat() if last_checked else None,
                }
            )

        return summaries

    # -- Default Evaluator Validation -----------------------------------------

    def check_default_evaluator(self) -> dict[str, Any]:
        """Validate defaults (DEFAULT_EVALUATOR_PROVIDER / DEFAULT_EVALUATOR_MODEL).

        Returns status, warning if unavailable, and a suggested available alternative.
        """
        provider_key = settings.default_evaluator_provider
        model_id = settings.default_evaluator_model

        if not provider_key or not model_id:
            suggestion = None
            if settings.enable_llm_judge:
                latest = self.get_all_latest()
                avail = [r for r in latest if r.status == "AVAILABLE" and self.is_record_fresh(r)]
                if avail:
                    suggestion = {"provider": avail[0].provider, "model_id": avail[0].model_id}

            return {
                "configured": False,
                "provider": provider_key,
                "model": model_id,
                "status": "not_configured",
                "warning": (
                    "Default evaluator is not configured (DEFAULT_EVALUATOR_PROVIDER / DEFAULT_EVALUATOR_MODEL)."
                    if settings.enable_llm_judge
                    else None
                ),
                "suggested_alternative": suggestion,
            }

        provider = get_provider(provider_key)
        if not provider or not provider.is_configured:
            suggestion = None
            latest = self.get_all_latest()
            avail = [r for r in latest if r.status == "AVAILABLE" and self.is_record_fresh(r)]
            if avail:
                suggestion = {"provider": avail[0].provider, "model_id": avail[0].model_id}
            return {
                "configured": True,
                "provider": provider_key,
                "model": model_id,
                "status": "unconfigured_provider",
                "warning": f"Default evaluator provider '{provider_key}' is not configured (missing credentials or not enabled).",
                "suggested_alternative": suggestion,
            }

        rec = self.get_latest_for_model(provider_key, model_id)
        if not rec:
            return {
                "configured": True,
                "provider": provider_key,
                "model": model_id,
                "status": "unverified",
                "warning": f"Default evaluator model '{model_id}' on '{provider_key}' has not been audited yet.",
                "suggested_alternative": None,
            }

        fresh = self.is_record_fresh(rec)
        if rec.status == "AVAILABLE" and fresh:
            return {
                "configured": True,
                "provider": provider_key,
                "model": model_id,
                "status": "available",
                "warning": None,
                "suggested_alternative": None,
            }

        latest = self.get_all_latest()
        same_p_avail = [
            r for r in latest if r.provider == provider_key and r.status == "AVAILABLE" and self.is_record_fresh(r)
        ]
        other_avail = [r for r in latest if r.status == "AVAILABLE" and self.is_record_fresh(r)]
        alt = same_p_avail[0] if same_p_avail else (other_avail[0] if other_avail else None)
        suggestion = {"provider": alt.provider, "model_id": alt.model_id} if alt else None

        reason = rec.reason or rec.status
        if not fresh and rec.status == "AVAILABLE":
            warning = f"Default evaluator model '{model_id}' audit record is stale (TTL expired). Run an audit or recheck."
            status = "stale"
        else:
            warning = f"Default evaluator model '{model_id}' on '{provider_key}' is {rec.status}: {reason}."
            status = rec.status.lower()

        return {
            "configured": True,
            "provider": provider_key,
            "model": model_id,
            "status": status,
            "warning": warning,
            "suggested_alternative": suggestion,
        }
