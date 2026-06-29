"""Tests for the nba_stats ``_execute`` transport mapping with a mocked endpoint factory.

No network: the "transport" is a factory callable we control. Retries are disabled (one attempt)
so no real backoff sleeps occur.
"""

import json

import nbaforecast.ingestion.clients.nba_stats as nba_stats
import pytest
import requests
from nbaforecast.errors import IngestionError, RateLimitError, TransientIngestionError


class NoOpThrottle:
    def __init__(self) -> None:
        self.waits = 0

    def wait(self) -> None:
        self.waits += 1


@pytest.fixture(autouse=True)
def patched_transport(monkeypatch: pytest.MonkeyPatch) -> NoOpThrottle:
    """Disable real throttling and cap retries at one attempt (no backoff sleeps)."""
    throttle = NoOpThrottle()
    monkeypatch.setattr(nba_stats, "get_throttle", lambda: throttle)

    class FakeSettings:
        ingest_max_retries = 1

    monkeypatch.setattr(
        "nbaforecast.ingestion.clients.retrying.get_settings", lambda: FakeSettings()
    )
    return throttle


def _http_error(status: int) -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.exceptions.HTTPError(response=response)


def test_success_returns_payload_and_throttles(patched_transport: NoOpThrottle) -> None:
    payload = {"resultSets": []}
    result = nba_stats._execute(lambda: payload)
    assert result is payload
    assert patched_transport.waits == 1


def test_429_maps_to_rate_limit_error() -> None:
    def factory() -> dict[str, object]:
        raise _http_error(429)

    with pytest.raises(RateLimitError):
        nba_stats._execute(factory)


def test_500_maps_to_transient_error() -> None:
    def factory() -> dict[str, object]:
        raise _http_error(503)

    with pytest.raises(TransientIngestionError):
        nba_stats._execute(factory)


def test_4xx_maps_to_non_retryable_ingestion_error() -> None:
    def factory() -> dict[str, object]:
        raise _http_error(400)

    with pytest.raises(IngestionError) as exc_info:
        nba_stats._execute(factory)
    assert not isinstance(exc_info.value, TransientIngestionError)


def test_timeout_maps_to_transient_error() -> None:
    def factory() -> dict[str, object]:
        raise requests.exceptions.Timeout("slow")

    with pytest.raises(TransientIngestionError):
        nba_stats._execute(factory)


def test_non_json_response_maps_to_transient_error() -> None:
    def factory() -> dict[str, object]:
        raise json.JSONDecodeError("Expecting value", "<html>", 0)

    with pytest.raises(TransientIngestionError):
        nba_stats._execute(factory)
