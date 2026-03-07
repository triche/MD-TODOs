"""Retry logic with exponential backoff for AI provider calls.

Provides a decorator / wrapper that retries on transient API errors
(rate-limits, server errors, timeouts) with configurable back-off.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

logger = logging.getLogger("md_todos.ai.retry")

P = ParamSpec("P")
R = TypeVar("R")

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0


class RetryConfig:
    """Configuration for retry behaviour."""

    __slots__ = ("backoff_factor", "base_delay", "max_delay", "max_retries")

    def __init__(
        self,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor


def _compute_delay(attempt: int, config: RetryConfig) -> float:
    """Compute the sleep duration for a given attempt (0-indexed)."""
    delay = config.base_delay * (config.backoff_factor**attempt)
    return min(delay, config.max_delay)


def with_retry(
    config: RetryConfig | None = None,
    retryable: tuple[type[BaseException], ...] = (),
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator that adds exponential-backoff retry to an async function.

    Args:
        config: Retry parameters. Uses defaults if *None*.
        retryable: Exception types that should trigger a retry.

    Returns:
        A decorated function that retries on *retryable* exceptions.
    """
    cfg = config or RetryConfig()

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: BaseException | None = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except retryable as exc:
                    last_exc = exc
                    if attempt < cfg.max_retries:
                        delay = _compute_delay(attempt, cfg)
                        logger.warning(
                            "Attempt %d/%d for %s failed (%s). Retrying in %.1fs…",
                            attempt + 1,
                            cfg.max_retries + 1,
                            fn.__qualname__,
                            exc,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "All %d attempts for %s exhausted. Last error: %s",
                            cfg.max_retries + 1,
                            fn.__qualname__,
                            exc,
                        )
            # Should not reach here, but satisfy type-checker
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
