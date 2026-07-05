"""Unit tests for the Chrome-impersonated stats.nba.com transport (impersonate.py)."""

from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
import requests
from curl_cffi import requests as curl_requests
from nbaforecast.ingestion.clients import impersonate


class _FakeCurlResponse:
    status_code = 200
    content = b'{"ok": true}'
    headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}
    url = "https://stats.nba.com/stats/leaguegamelog"
    encoding = "utf-8"


class _FakeCurlSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._error = error

    def request(self, **kwargs: Any) -> _FakeCurlResponse:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _FakeCurlResponse()


@pytest.fixture
def transport() -> Iterator[_FakeCurlSession]:
    impersonate.install_impersonated_transport()
    fake = _FakeCurlSession()
    impersonate._curl_session = fake
    try:
        yield fake
    finally:
        impersonate.uninstall_impersonated_transport()


def test_stats_nba_requests_route_through_curl_session(transport: _FakeCurlSession) -> None:
    response = requests.get(
        "https://stats.nba.com/stats/leaguegamelog", params={"LeagueID": "00"}, timeout=5
    )

    assert isinstance(response, requests.Response)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["Content-Type"] == "application/json"
    assert len(transport.calls) == 1
    assert transport.calls[0]["params"] == {"LeagueID": "00"}
    assert transport.calls[0]["timeout"] == 5
    # requests-specific plumbing kwargs must not leak through to curl_cffi.
    assert "stream" not in transport.calls[0]


def test_other_hosts_use_the_original_transport(
    transport: _FakeCurlSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def sentinel(self: requests.Session, method: Any, url: Any, **kwargs: Any) -> str:
        seen.append(str(url))
        return "original-path"

    monkeypatch.setattr(impersonate, "_original_request", sentinel)

    result = requests.Session().request("GET", "https://example.com/data")

    assert result == "original-path"
    assert seen == ["https://example.com/data"]
    assert transport.calls == []


def test_curl_timeout_is_reraised_as_requests_timeout(transport: _FakeCurlSession) -> None:
    impersonate._curl_session = _FakeCurlSession(error=curl_requests.exceptions.Timeout("slow"))

    with pytest.raises(requests.exceptions.Timeout):
        requests.get("https://stats.nba.com/stats/leaguegamelog", timeout=1)


def test_curl_connection_error_is_reraised_as_requests_connection_error(
    transport: _FakeCurlSession,
) -> None:
    impersonate._curl_session = _FakeCurlSession(
        error=curl_requests.exceptions.ConnectionError("nope")
    )

    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get("https://stats.nba.com/stats/leaguegamelog", timeout=1)


def test_install_is_idempotent_and_uninstall_restores() -> None:
    original = requests.sessions.Session.request
    impersonate.install_impersonated_transport()
    patched = requests.sessions.Session.request
    impersonate.install_impersonated_transport()
    assert requests.sessions.Session.request is patched

    impersonate.uninstall_impersonated_transport()
    assert requests.sessions.Session.request is original
