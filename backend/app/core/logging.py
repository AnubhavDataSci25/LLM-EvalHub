"""Structured-ish logging setup. Never logs provider credentials."""

from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings

_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9\-_]{8,}|nvapi-[A-Za-z0-9\-_]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z\-_]{20,}|hf_[A-Za-z0-9]{8,})"
)


class RedactingFilter(logging.Filter):
    """Redacts anything that looks like an API key before it reaches a handler."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if isinstance(record.msg, str):
            record.msg = _SECRET_PATTERN.sub("***redacted***", record.msg)
        if record.args:
            try:
                record.args = tuple(
                    _SECRET_PATTERN.sub("***redacted***", a) if isinstance(a, str) else a
                    for a in record.args
                )
            except Exception:  # pragma: no cover - defensive
                pass
        return True


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
