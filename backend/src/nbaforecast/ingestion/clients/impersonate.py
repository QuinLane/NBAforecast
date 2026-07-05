"""Chrome-impersonated TLS transport for stats.nba.com (M3.5 connectivity fix).

Akamai's bot manager on stats.nba.com stalls non-browser TLS fingerprints: the TCP + TLS
handshake completes and the HTTP response simply never arrives. Verified 2026-07-05 from
multiple networks (residential, cellular, US VPN, US cloud): plain curl / python-requests /
.NET all hang, while a byte-identical Chrome handshake via ``curl_cffi`` gets HTTP 200.

Both of this project's ingestion paths (``nba_api`` endpoints and ``pbpstats``'s internal
fetches) ultimately call ``requests.Session.request``, so one scoped patch fixes every
stats.nba.com call without forking either library: requests to ``IMPERSONATED_HOSTS`` are
served by a shared ``curl_cffi`` session and adapted back into a **genuine**
``requests.Response`` (and ``requests`` exception types), so the retry/error mapping in
``nba_stats.py`` / ``pbp.py`` keeps working unchanged. All other hosts pass through to the
original implementation untouched.
"""

import logging
import threading
from typing import Any, Final
from urllib.parse import urlsplit

import requests
import requests.structures
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

IMPERSONATED_HOSTS = frozenset({"stats.nba.com"})
IMPERSONATE_PROFILE: Final = "chrome"

_lock = threading.Lock()
_original_request: Any = None
_curl_session: Any = None


def _to_requests_response(curl_response: Any) -> requests.Response:
    """Adapt a curl_cffi response into a real ``requests.Response``.

    Downstream code (nba_api, pbpstats, our clients) only touches ``status_code`` /
    ``text`` / ``json()`` / ``content`` / ``headers`` / ``raise_for_status()`` — all of
    which work off the fields set here.
    """
    response = requests.Response()
    response.status_code = int(curl_response.status_code)
    response._content = curl_response.content
    response.headers = requests.structures.CaseInsensitiveDict(dict(curl_response.headers))
    response.url = str(curl_response.url)
    response.encoding = curl_response.encoding
    return response


def _impersonated_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Serve one request through the shared impersonating session.

    Only the kwargs the wrapped libraries actually use are forwarded; requests-specific
    plumbing kwargs (stream/verify/cert/hooks/...) that curl_cffi doesn't understand are
    dropped. curl_cffi failures are re-raised as their ``requests`` equivalents so callers'
    ``except requests.exceptions...`` clauses behave identically.
    """
    forwarded = {
        key: kwargs[key]
        for key in ("params", "data", "json", "headers", "timeout", "proxies", "allow_redirects")
        if kwargs.get(key) is not None
    }
    try:
        curl_response = _curl_session.request(method=method, url=url, **forwarded)
    except curl_requests.exceptions.Timeout as exc:
        raise requests.exceptions.Timeout(str(exc)) from exc
    except curl_requests.exceptions.RequestException as exc:
        raise requests.exceptions.ConnectionError(str(exc)) from exc
    return _to_requests_response(curl_response)


def install_impersonated_transport() -> None:
    """Patch ``requests.Session.request`` to impersonate Chrome for ``IMPERSONATED_HOSTS``.

    Idempotent and thread-safe; all non-matching hosts go through the original code path.
    """
    global _original_request, _curl_session
    with _lock:
        if _original_request is not None:
            return
        _curl_session = curl_requests.Session(impersonate=IMPERSONATE_PROFILE)
        _original_request = requests.sessions.Session.request

        def request(self: requests.Session, method: Any, url: Any, **kwargs: Any) -> Any:
            if urlsplit(str(url)).hostname in IMPERSONATED_HOSTS:
                return _impersonated_request(str(method), str(url), **kwargs)
            return _original_request(self, method, url, **kwargs)

        requests.sessions.Session.request = request  # type: ignore[method-assign, assignment]
        logger.info(
            "impersonated transport installed for %s (profile=%s)",
            sorted(IMPERSONATED_HOSTS),
            IMPERSONATE_PROFILE,
        )


def uninstall_impersonated_transport() -> None:
    """Restore the original ``requests`` transport (used by tests)."""
    global _original_request, _curl_session
    with _lock:
        if _original_request is None:
            return
        requests.sessions.Session.request = _original_request  # type: ignore[method-assign]
        _original_request = None
        _curl_session = None
