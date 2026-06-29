"""Shared request throttle — enforces a minimum interval between upstream calls.

stats.nba.com blocks aggressive callers, so every client request passes through one
process-global :class:`Throttle` (a single concurrency lane with a min-interval gate). The
clock and sleep functions are injectable so the gate is unit-testable without real waiting.
"""

import threading
import time
from collections.abc import Callable

from nbaforecast.config.settings import get_settings


class Throttle:
    """Thread-safe minimum-interval gate.

    Args:
        min_interval: Minimum seconds between successive :meth:`wait` returns.
        clock: Monotonic time source (injectable for tests).
        sleep: Blocking sleep function (injectable for tests).
    """

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_call: float | None = None

    def wait(self) -> None:
        """Block until at least ``min_interval`` has elapsed since the previous call."""
        with self._lock:
            if self._last_call is not None:
                remaining = self._min_interval - (self._clock() - self._last_call)
                if remaining > 0:
                    self._sleep(remaining)
            self._last_call = self._clock()


_throttle: Throttle | None = None
_throttle_lock = threading.Lock()


def get_throttle() -> Throttle:
    """Return the process-global throttle, built from settings on first use."""
    global _throttle
    if _throttle is None:
        with _throttle_lock:
            if _throttle is None:
                _throttle = Throttle(get_settings().ingest_throttle_seconds)
    return _throttle
