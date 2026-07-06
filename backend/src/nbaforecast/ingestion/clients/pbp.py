"""Thin wrapper over ``pbpstats`` for possession + lineup data (the RAPM substrate).

``pbpstats`` parses NBA play-by-play into possession objects carrying on-court lineups. We
extract a clean, JSON-serializable dict per possession (its ``.data`` is a live object graph,
not serializable) with exactly the fields the ``possessions`` table needs. T1.4 parses these.

The pbpstats accessors used here (start/end clock, offense team, per-event ``current_players``,
made-shot values) are confirmed against a live game at T1.7.
"""

import logging
from pathlib import Path
from typing import Any

import requests
from pbpstats.client import Client
from pbpstats.resources.enhanced_pbp.field_goal import FieldGoal
from pbpstats.resources.enhanced_pbp.free_throw import FreeThrow
from pbpstats.resources.enhanced_pbp.live.enhanced_pbp_item import LiveEnhancedPbpItem
from pbpstats.resources.enhanced_pbp.start_of_period import InvalidNumberOfStartersException

from nbaforecast.config.settings import get_settings
from nbaforecast.errors import IngestionError, TransientIngestionError
from nbaforecast.ingestion.clients.impersonate import install_impersonated_transport
from nbaforecast.ingestion.clients.retrying import retry
from nbaforecast.ingestion.clients.throttle import get_throttle

logger = logging.getLogger(__name__)

# cdn liveData period-boundary actions omit "teamId", so pbpstats' live items never get a
# team_id attribute — but its possession builder reads event.team_id unguarded
# (AttributeError, found live at M3.5). Class-level default mirrors pbpstats' own
# "no team" sentinel (it filters `team_id != 0` everywhere).
LiveEnhancedPbpItem.team_id = 0

JsonDict = dict[str, Any]


def _client() -> Client:
    """Build a pbpstats client using the web source and on-disk cache.

    Provider is ``live`` (cdn.nba.com liveData): the ``stats_nba`` provider's underlying v2
    endpoints were retired by the NBA (M3.5). cdn liveData covers 2019-20 → present — enough
    for RAPM's default 3-season window; pre-2019 possessions are currently unavailable
    (historical-RAPM limitation, documented in plans/data-pipeline.md).
    """
    cache_dir = Path(get_settings().pbpstats_cache_dir)
    # pbpstats writes into these subdirectories but never creates them (FileNotFoundError
    # on a fresh cache, found live at M3.5).
    for subdir in ("game_details", "pbp"):
        (cache_dir / subdir).mkdir(parents=True, exist_ok=True)
    settings = {
        "dir": str(cache_dir),
        "Boxscore": {"source": "web", "data_provider": "live"},
        "Possessions": {"source": "web", "data_provider": "live"},
    }
    return Client(settings)


def _clock_to_seconds(clock: Any) -> int | None:
    if not clock or ":" not in str(clock):
        return None
    minutes, seconds = str(clock).split(":")
    return int(minutes) * 60 + int(float(seconds))


def _possession_points(events: list[Any]) -> int:
    """Points scored on a possession = made FG values + made FTs."""
    points = 0
    for event in events:
        if isinstance(event, FieldGoal) and event.is_made:
            points += event.shot_value
        elif isinstance(event, FreeThrow) and event.is_made:
            points += 1
    return points


def _possession_dict(possession: Any) -> JsonDict | None:
    offense = possession.offense_team_id
    team_ids = list(possession.get_team_ids())
    if offense not in team_ids:
        return None  # malformed/transition possession with no clear offense — skip
    defense = next(t for t in team_ids if t != offense)
    lineups = possession.events[0].current_players if possession.events else {}
    return {
        "period": possession.period,
        "start_seconds": _clock_to_seconds(possession.start_time),
        "end_seconds": _clock_to_seconds(possession.end_time),
        "offense_team_id": offense,
        "defense_team_id": defense,
        "points": _possession_points(possession.events),
        "off_player_ids": list(lineups.get(offense, [])),
        "def_player_ids": list(lineups.get(defense, [])),
    }


@retry
def fetch_possessions(game_id: str) -> list[JsonDict]:
    """Return clean possession dicts (period, clock, teams, points, lineups) for a game."""
    if get_settings().ingest_impersonate:
        install_impersonated_transport()
    get_throttle().wait()
    try:
        game = _client().Game(game_id)
        return [d for p in game.possessions.items if (d := _possession_dict(p)) is not None]
    except InvalidNumberOfStartersException as exc:
        # pbpstats can't always derive period starters from pbp alone (seen live at M3.5 on
        # an OT period). Losing one game's possessions is negligible for RAPM; losing the
        # game's boxscore/pbp/shots to an all-or-nothing rollback is not — so warn and land
        # the game without possessions.
        logger.warning("no possessions for %s (unresolvable starters): %s", game_id, exc)
        return []
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise TransientIngestionError(f"pbpstats connection error: {exc}") from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status is not None and (status == 429 or status >= 500):
            raise TransientIngestionError(f"pbpstats HTTP {status}") from exc
        raise IngestionError(f"pbpstats HTTP {status}") from exc
    except (KeyError, ValueError, AttributeError) as exc:
        raise IngestionError(f"pbpstats could not build possessions for {game_id}: {exc}") from exc
