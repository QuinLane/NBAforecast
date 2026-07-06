"""Bronze→silver ingestion orchestration (source-agnostic of Prefect, so it is unit-testable).

``ingest_schedule`` lands a season's games; ``ingest_game`` lands one game's box score, pbp,
shots, and possessions. Each entity follows the same path: fetch (client) → land raw (bronze) →
parse → validate-and-load (silver). The Prefect flows in :mod:`nbaforecast.ingestion.flows` wrap
these with retries, concurrency, and scheduling.
"""

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.ingestion.clients.nba_stats import (
    fetch_boxscore,
    fetch_pbp,
    fetch_schedule,
    fetch_shots,
)
from nbaforecast.ingestion.clients.pbp import fetch_possessions
from nbaforecast.ingestion.load import load_silver
from nbaforecast.ingestion.parse import (
    parse_games,
    parse_play_by_play,
    parse_player_game_stats,
    parse_possessions,
    parse_shots,
    parse_team_game_stats,
)
from nbaforecast.ingestion.seed import ensure_players_from_boxscore
from nbaforecast.storage.object_store import ObjectStore

logger = logging.getLogger(__name__)

STATS_SOURCE = "stats_nba"
PBP_SOURCE = "pbpstats"


@dataclass(slots=True)
class GameMeta:
    """Identity a per-game ingest needs (carried from the schedule)."""

    game_id: str
    season: str
    season_start_year: int
    home_team_id: int


def _season_start_year(season: str) -> int:
    return int(season[:4])


def season_for_date(day: date) -> str:
    """NBA season string containing ``day`` (the season spans Oct→Jun)."""
    start_year = day.year if day.month >= 10 else day.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


async def ingest_schedule(
    session: AsyncSession,
    store: ObjectStore,
    season: str,
    season_type: str = "Regular Season",
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[GameMeta]:
    """Land the ``games`` table for a season (optional date window); return per-game metas."""
    raw = fetch_schedule(season, season_type, date_from=date_from, date_to=date_to)
    year = _season_start_year(season)
    store.put_raw(STATS_SOURCE, "schedule", season, f"{season}-{season_type}", raw)
    df = parse_games(raw)
    await load_silver(
        session,
        store,
        "games",
        df,
        season_start_year=year,
        partition_key=str(year),
        raw_payload=raw,
        source=STATS_SOURCE,
        endpoint="schedule",
    )
    return [
        GameMeta(
            game_id=row["game_id"],
            season=season,
            season_start_year=year,
            home_team_id=int(row["home_team_id"]),
        )
        for row in df.to_dict("records")
    ]


async def ingest_game(session: AsyncSession, store: ObjectStore, meta: GameMeta) -> set[str]:
    """Land box score, play-by-play, shots, and possessions for one game.

    Returns the set of ingested entity names (for the checkpoint).
    """
    gid, season, year = meta.game_id, meta.season, meta.season_start_year

    box_raw = fetch_boxscore(gid)
    store.put_raw(STATS_SOURCE, "boxscore", season, gid, box_raw)
    # Players who debuted after nba_api's static index (rookies, two-way signings) would
    # FK-violate player_game_stats — seed them from the boxscore itself (self-healing).
    await ensure_players_from_boxscore(session, box_raw)
    await load_silver(
        session,
        store,
        "team_game_stats",
        parse_team_game_stats(box_raw, meta.home_team_id),
        season_start_year=year,
        partition_key=gid,
        raw_payload=box_raw,
        source=STATS_SOURCE,
        endpoint="boxscore",
    )
    await load_silver(
        session,
        store,
        "player_game_stats",
        parse_player_game_stats(box_raw, meta.home_team_id),
        season_start_year=year,
        partition_key=gid,
        raw_payload=box_raw,
        source=STATS_SOURCE,
        endpoint="boxscore",
    )

    pbp_raw = fetch_pbp(gid)
    store.put_raw(STATS_SOURCE, "pbp", season, gid, pbp_raw)
    await load_silver(
        session,
        store,
        "play_by_play",
        parse_play_by_play(pbp_raw),
        season_start_year=year,
        partition_key=gid,
        raw_payload=pbp_raw,
        source=STATS_SOURCE,
        endpoint="pbp",
    )

    shots_raw = fetch_shots(gid, season=season)
    store.put_raw(STATS_SOURCE, "shots", season, gid, shots_raw)
    await load_silver(
        session,
        store,
        "shots",
        parse_shots(shots_raw, year),
        season_start_year=year,
        partition_key=gid,
        raw_payload=shots_raw,
        source=STATS_SOURCE,
        endpoint="shots",
    )

    poss_raw = fetch_possessions(gid)
    store.put_raw(PBP_SOURCE, "possessions", season, gid, poss_raw)
    await load_silver(
        session,
        store,
        "possessions",
        parse_possessions(poss_raw, gid),
        season_start_year=year,
        partition_key=gid,
        raw_payload=poss_raw,
        source=PBP_SOURCE,
        endpoint="possessions",
        game_id=gid,
    )

    logger.info("ingested game %s", gid)
    return {"boxscore", "pbp", "shots", "possessions"}
