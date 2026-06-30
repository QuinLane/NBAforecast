"""Unit tests for the request throttle (no real time elapses — clock/sleep are injected)."""

from nbaforecast.ingestion.clients.throttle import Throttle


class FakeClock:
    """Deterministic monotonic clock that advances only when ``sleep`` is called."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_first_call_does_not_sleep() -> None:
    clock = FakeClock()
    throttle = Throttle(0.6, clock=clock.time, sleep=clock.sleep)
    throttle.wait()
    assert clock.sleeps == []


def test_back_to_back_calls_sleep_remaining_interval() -> None:
    clock = FakeClock()
    throttle = Throttle(0.6, clock=clock.time, sleep=clock.sleep)
    throttle.wait()  # t=0, records last_call=0
    throttle.wait()  # no time passed → must sleep the full interval
    assert clock.sleeps == [0.6]


def test_partial_elapsed_sleeps_only_the_remainder() -> None:
    clock = FakeClock()
    throttle = Throttle(0.6, clock=clock.time, sleep=clock.sleep)
    throttle.wait()
    clock.now += 0.2  # 0.2s passes between calls
    throttle.wait()
    assert clock.sleeps == [0.6 - 0.2]


def test_enough_elapsed_means_no_sleep() -> None:
    clock = FakeClock()
    throttle = Throttle(0.6, clock=clock.time, sleep=clock.sleep)
    throttle.wait()
    clock.now += 1.0  # more than the interval has passed
    throttle.wait()
    assert clock.sleeps == []
