"""Structured logging setup with credential, token, and password redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from contextvars import ContextVar

from app.core.config import settings

# Context variables for request tracing and tenant correlation
request_id_ctx: ContextVar[str] = ContextVar("request_id_ctx", default="-")
workspace_id_ctx: ContextVar[str] = ContextVar("workspace_id_ctx", default="-")

# Credential patterns to scrub from all logs
_PROVIDER_KEY_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9\-_]{8,}|nvapi-[A-Za-z0-9\-_]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z\-_]{20,}|hf_[A-Za-z0-9]{8,})"
)
_BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*|[A-Za-z0-9\-_.]{16,})")
_SENSITIVE_KV_PATTERN = re.compile(
    r"""(?i)(["']?(?:password|hashed_password|refresh_token|token|secret|client_secret|encryption_key)["']?\s*[:=\s]\s*["'])([^"']{3,})(["'])"""
)


def redact_secrets(text: str) -> str:
    """Scrub provider keys, bearer tokens, passwords, and refresh tokens from a string."""
    if not isinstance(text, str):
        return text
    text = _PROVIDER_KEY_PATTERN.sub("***redacted***", text)
    text = _BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED]", text)
    text = _SENSITIVE_KV_PATTERN.sub(r"\g<1>[REDACTED]\g<3>", text)
    return text


class RedactingFilter(logging.Filter):
    """Redacts secrets, bearer tokens, and passwords before reaching log handlers."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
            record.msg = redact_secrets(msg)
            record.args = ()
        except Exception:
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg)
            if record.args:
                try:
                    record.args = tuple(
                        redact_secrets(a) if isinstance(a, str) else a
                        for a in record.args
                    )
                except Exception:
                    pass
        return True


class StructuredContextFilter(logging.Filter):
    """Injects current request_id and workspace_id from contextvars into log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = request_id_ctx.get("-")
        record.workspace_id = workspace_id_ctx.get("-")
        return True


class JsonLogFormatter(logging.Formatter):
    """Outputs structured JSON lines for production log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "workspace_id": getattr(record, "workspace_id", "-"),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)

    if settings.log_format.lower() == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | [%(request_id)s|%(workspace_id)s] %(name)s | %(message)s"
            )
        )

    handler.addFilter(StructuredContextFilter())
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
