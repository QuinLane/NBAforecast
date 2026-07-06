"""Thin wrappers over ``nba_api`` stats endpoints.

Every call passes through the shared throttle and the retry decorator. Functions return the
raw parsed JSON (``get_dict()``) with **no transformation** — parsing/validation is T1.4's job.
Network/JSON failures are mapped onto :class:`~nbaforecast.errors.TransientIngestionError` (or
:class:`~nbaforecast.errors.RateLimitError` for HTTP 429) so :func:`retry` handles them.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import requests

# v3 boxscore/pbp endpoints: the NBA retired the v2 ones (empty payloads for every era,
# discovered live at M3.5); v3 covers the full 1996+ era.
from nba_api.stats.endpoints import (
    boxscoreadvancedv3,
    boxscoretraditionalv3,
    leaguegamelog,
    playbyplayv3,
    shotchartdetail,
)

from nbaforecast.config.settings import get_settings
from nbaforecast.errors import IngestionError, RateLimitError, TransientIngestionError
from nbaforecast.ingestion.clients.impersonate import install_impersonated_transport
from nbaforecast.ingestion.clients.retrying import retry
from nbaforecast.ingestion.clients.throttle import get_throttle

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]

DEFAULT_SEASON_TYPE = "Regular Season"

# Headers stats.nba.com expects; without the x-nba-stats-* pair requests are frequently dropped.
_BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Host": "stats.nba.com",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}


def stats_headers() -> dict[str, str]:
    """Realistic request headers, with the configured User-Agent."""
    return {**_BASE_HEADERS, "User-Agent": get_settings().ingest_user_agent}


@retry
def _execute(factory: Callable[[], JsonDict]) -> JsonDict:
    """Throttle, run an endpoint factory, and map transient failures for retry."""
    if get_settings().ingest_impersonate:
        install_impersonated_transport()
    get_throttle().wait()
    try:
        return factory()
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 429:
            raise RateLimitError("stats.nba.com rate limit (429)") from exc
        if status is not None and status >= 500:
            raise TransientIngestionError(f"stats.nba.com {status}") from exc
        raise IngestionError(f"stats.nba.com HTTP {status}") from exc
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise TransientIngestionError(f"stats.nba.com connection error: {exc}") from exc
    except json.JSONDecodeError as exc:
        # Rate-limit / maintenance pages return HTML; treat as transient and back off.
        raise TransientIngestionError("non-JSON response from stats.nba.com") from exc
    except (KeyError, TypeError) as exc:
        # nba_api itself crashes when an error payload lacks resultSets (KeyError
        # 'resultSet', seen live at M3.5 on boxscoreadvancedv2) — same transient server
        # garbage as the HTML case above, just in JSON clothing.
        raise TransientIngestionError(f"malformed stats.nba.com payload: {exc!r}") from exc


def fetch_schedule(
    season: str,
    season_type: str = DEFAULT_SEASON_TYPE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> JsonDict:
    """Return the raw team game log for a season (one row per team per game).

    Args:
        season: NBA season string, e.g. ``"2023-24"``.
        season_type: ``Regular Season`` / ``Playoffs`` / ``Pre Season`` / ``Play In``.
        date_from: Optional ``MM/DD/YYYY`` lower bound (used by the daily flow).
        date_to: Optional ``MM/DD/YYYY`` upper bound.
    """
    timeout = get_settings().ingest_request_timeout
    return _execute(
        lambda: leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star=season_type,
            player_or_team_abbreviation="T",
            date_from_nullable=date_from or "",
            date_to_nullable=date_to or "",
            headers=stats_headers(),
            timeout=timeout,
        ).get_dict()
    )


def fetch_boxscore(game_id: str) -> JsonDict:
    """Return raw traditional + advanced box scores for a game.

    Both endpoints are needed downstream: traditional carries counting stats, advanced carries
    off/def rating, pace, and possessions. Returned as ``{"traditional": ..., "advanced": ...}``
    without merging.
    """
    headers = stats_headers()
    timeout = get_settings().ingest_request_timeout
    traditional = _execute(
        lambda: boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id, headers=headers, timeout=timeout
        ).get_dict()
    )
    advanced = _execute(
        lambda: boxscoreadvancedv3.BoxScoreAdvancedV3(
            game_id=game_id, headers=headers, timeout=timeout
        ).get_dict()
    )
    return {"traditional": traditional, "advanced": advanced}


def fetch_pbp(game_id: str) -> JsonDict:
    """Return raw play-by-play for a game."""
    timeout = get_settings().ingest_request_timeout
    return _execute(
        lambda: playbyplayv3.PlayByPlayV3(
            game_id=game_id, headers=stats_headers(), timeout=timeout
        ).get_dict()
    )


def fetch_shots(
    game_id: str,
    season: str | None = None,
    season_type: str = DEFAULT_SEASON_TYPE,
) -> JsonDict:
    """Return raw shot-chart detail (all field-goal attempts) for a game.

    ``team_id=0`` / ``player_id=0`` selects every shooter; ``season`` narrows the lookup and is
    recommended where known.
    """
    timeout = get_settings().ingest_request_timeout
    return _execute(
        lambda: shotchartdetail.ShotChartDetail(
            team_id=0,
            player_id=0,
            context_measure_simple="FGA",
            game_id_nullable=game_id,
            season_nullable=season,
            season_type_all_star=season_type,
            headers=stats_headers(),
            timeout=timeout,
        ).get_dict()
    )
