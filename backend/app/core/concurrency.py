"""Bounded concurrency + retry helpers.

Rules enforced here:
  * never launch unbounded parallel provider calls,
  * never retry forever,
  * honour `Retry-After` when the provider supplies it.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import TypeVar

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


async def run_bounded(
    items: Sequence[T],
    worker: Callable[[T], Awaitable[R]],
    *,
    limit: int | None = None,
) -> list[R]:
    """Run `worker` over `items` with a hard concurrency ceiling, preserving order."""
    limit = max(1, limit or settings.max_concurrent_requests)
    semaphore = asyncio.Semaphore(limit)

    async def _guarded(item: T) -> R:
        async with semaphore:
            return await worker(item)

    return list(await asyncio.gather(*(_guarded(i) for i in items)))


async def with_retries(
    func: Callable[[], Awaitable[R]],
    *,
    attempts: int | None = None,
    base_delay: float | None = None,
    max_delay: float = 20.0,
    retry_on: Iterable[type[Exception]] = (ProviderError,),
) -> R:
    """Retry with exponential backoff + jitter. Bounded attempts, never infinite."""
    attempts = max(1, attempts if attempts is not None else settings.retry_attempts + 1)
    base_delay = base_delay if base_delay is not None else settings.retry_backoff_seconds
    retry_on = tuple(retry_on)
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            retryable = getattr(exc, "retryable", False)
            if not retryable or attempt == attempts:
                raise
            hinted = getattr(exc, "retry_after", None)
            delay = float(hinted) if hinted else min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, 0.25)
            logger.warning(
                "retrying after %.2fs (attempt %s/%s): %s", delay, attempt, attempts, exc
            )
            await asyncio.sleep(delay)
    assert last_exc is not None  # pragma: no cover
    raise last_exc
