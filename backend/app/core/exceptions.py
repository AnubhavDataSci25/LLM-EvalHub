"""Domain exceptions and the consistent error payload used by the API."""

from __future__ import annotations

from typing import Any


class EvalHubError(Exception):
    """Base error. Every API error response derives from this shape."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class NotFoundError(EvalHubError):
    status_code = 404
    code = "not_found"


class ValidationFailedError(EvalHubError):
    status_code = 422
    code = "validation_failed"


class ConflictError(EvalHubError):
    status_code = 409
    code = "conflict"


class ProviderError(EvalHubError):
    """Raised by provider adapters. Carries a machine-readable kind."""

    status_code = 502
    code = "provider_error"

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        kind: str = "provider_error",
        retryable: bool = False,
        retry_after: float | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message, code=kind)
        self.provider = provider
        self.kind = kind
        self.retryable = retryable
        self.retry_after = retry_after
        self.status = status
        self.details = {
            "provider": provider,
            "kind": kind,
            "retryable": retryable,
            "retry_after": retry_after,
            "upstream_status": status,
        }


class ProviderNotConfiguredError(ProviderError):
    status_code = 400

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Provider '{provider}' is not configured. Add its API key to the backend .env file.",
            provider=provider,
            kind="provider_not_configured",
            retryable=False,
        )


class RateLimitedError(ProviderError):
    status_code = 429

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        super().__init__(
            f"Provider '{provider}' rate limited the request.",
            provider=provider,
            kind="rate_limited",
            retryable=True,
            retry_after=retry_after,
            status=429,
        )
