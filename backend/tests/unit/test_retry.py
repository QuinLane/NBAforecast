"""Unit tests for the retry decorator (sleep injected — no real backoff waiting)."""

import pytest
from nbaforecast.errors import IngestionError, RateLimitError, TransientIngestionError
from nbaforecast.ingestion.clients.retrying import retry


def test_returns_on_first_success() -> None:
    calls = 0

    @retry(max_attempts=5, sleep=lambda _: None)
    def ok() -> str:
        nonlocal calls
        calls += 1
        return "value"

    assert ok() == "value"
    assert calls == 1


def test_retries_then_succeeds() -> None:
    calls = 0

    @retry(max_attempts=5, sleep=lambda _: None)
    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientIngestionError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls == 3


def test_raises_after_exhausting_attempts() -> None:
    calls = 0

    @retry(max_attempts=3, sleep=lambda _: None)
    def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise RateLimitError("429")

    with pytest.raises(RateLimitError):
        always_fails()
    assert calls == 3


def test_non_retryable_exception_propagates_immediately() -> None:
    calls = 0

    @retry(max_attempts=5, sleep=lambda _: None)
    def bad_request() -> None:
        nonlocal calls
        calls += 1
        raise IngestionError("400 — do not retry")

    with pytest.raises(IngestionError):
        bad_request()
    assert calls == 1  # IngestionError is not in RETRYABLE_EXCEPTIONS


def test_backoff_delays_are_capped_and_exponential() -> None:
    delays: list[float] = []

    @retry(max_attempts=6, base_delay=0.5, max_delay=2.0, sleep=delays.append)
    def always_transient() -> None:
        raise TransientIngestionError("boom")

    with pytest.raises(TransientIngestionError):
        always_transient()
    # 5 sleeps before the 6th (final) attempt: 0.5, 1.0, 2.0(capped), 2.0, 2.0
    assert delays == [0.5, 1.0, 2.0, 2.0, 2.0]


def test_max_attempts_defaults_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSettings:
        ingest_max_retries = 2

    monkeypatch.setattr(
        "nbaforecast.ingestion.clients.retrying.get_settings", lambda: FakeSettings()
    )
    calls = 0

    @retry(sleep=lambda _: None)
    def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise TransientIngestionError("boom")

    with pytest.raises(TransientIngestionError):
        always_fails()
    assert calls == 2
