"""Thin wrapper over ``pbpstats`` for possession + lineup data (the RAPM substrate).

``pbpstats`` parses NBA play-by-play into possession objects carrying on-court lineups. We return
each possession's raw ``.data`` dict (no transformation); T1.4 parses these into the
``possessions`` table. Responses are cached on disk under ``pbpstats_cache_dir``.
"""

import logging
from pathlib import Path
from typing import Any

import requests
from pbpstats.client import Client

from nbaforecast.config.settings import get_settings
from nbaforecast.errors import IngestionError, TransientIngestionError
from nbaforecast.ingestion.clients.retrying import retry
from nbaforecast.ingestion.clients.throttle import get_throttle

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]


def _client() -> Client:
    """Build a pbpstats client using the web source and on-disk cache."""
    cache_dir = Path(get_settings().pbpstats_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    settings = {
        "dir": str(cache_dir),
        "Boxscore": {"source": "web", "data_provider": "stats_nba"},
        "Possessions": {"source": "web", "data_provider": "stats_nba"},
    }
    return Client(settings)


@retry
def fetch_possessions(game_id: str) -> list[JsonDict]:
    """Return the raw possession dicts (with lineups) for a game.

    Each item is a ``pbpstats`` possession's ``.data`` payload — start/end time, period,
    offense/defense team, points, and the events that carry on-court player ids.
    """
    get_throttle().wait()
    try:
        game = _client().Game(game_id)
        return [possession.data for possession in game.possessions.items]
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise TransientIngestionError(f"pbpstats connection error: {exc}") from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status is not None and (status == 429 or status >= 500):
            raise TransientIngestionError(f"pbpstats HTTP {status}") from exc
        raise IngestionError(f"pbpstats HTTP {status}") from exc
    except (KeyError, ValueError) as exc:
        # Malformed/absent possession data — a real data problem, not transient.
        raise IngestionError(f"pbpstats could not build possessions for {game_id}: {exc}") from exc
