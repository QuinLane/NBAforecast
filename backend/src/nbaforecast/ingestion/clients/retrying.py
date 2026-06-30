"""Exponential-backoff retry decorator for transient ingestion failures.

Retries only on :class:`~nbaforecast.errors.TransientIngestionError` (and subclasses such as
:class:`~nbaforecast.errors.RateLimitError`) by default; clients map network timeouts / HTTP 429
onto those types so non-transient bugs are never silently retried. After the final attempt the
last error propagates unchanged.
"""

import functools
import logging
import time
from collections.abc import Callable
from typing import overload

from nbaforecast.config.settings import get_settings
from nbaforecast.errors import TransientIngestionError

logger = logging.getLogger(__name__)

# Exceptions worth retrying. Clients translate requests/json failures into these.
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (TransientIngestionError,)


@overload
def retry[**P, R](func: Callable[P, R]) -> Callable[P, R]: ...


@overload
def retry[**P, R](
    *,
    max_attempts: int | None = ...,
    base_delay: float = ...,
    max_delay: float = ...,
    exceptions: tuple[type[Exception], ...] = ...,
    sleep: Callable[[float], None] = ...,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def retry[**P, R](
    func: Callable[P, R] | None = None,
    *,
    max_attempts: int | None = None,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple[type[Exception], ...] = RETRYABLE_EXCEPTIONS,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry the wrapped callable with capped exponential backoff.

    Usable bare (``@retry``) or parameterized (``@retry(max_attempts=3)``).

    Args:
        max_attempts: Total attempts before giving up. ``None`` reads ``ingest_max_retries``
            from settings at call time.
        base_delay: Delay before the first retry (seconds); doubles each attempt.
        max_delay: Upper bound on any single backoff sleep.
        exceptions: Exception types that trigger a retry.
        sleep: Sleep function (injectable for tests).
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            attempts = (
                max_attempts if max_attempts is not None else get_settings().ingest_max_retries
            )
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= attempts:
                        logger.error("%s failed after %d attempts: %s", fn.__name__, attempts, exc)
                        raise
                    delay = min(base_delay * 2 ** (attempt - 1), max_delay)
                    logger.warning(
                        "%s attempt %d/%d failed (%s); retrying in %.2fs",
                        fn.__name__,
                        attempt,
                        attempts,
                        exc,
                        delay,
                    )
                    sleep(delay)
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorator(func) if func is not None else decorator
