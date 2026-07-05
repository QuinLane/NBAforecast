"""Seed the ``teams`` / ``players`` reference tables from nba_api's static data (M3.5 fix).

``games`` and ``player_game_stats`` carry foreign keys onto ``teams`` / ``players``, but no
ingestion step ever populated them — unit tests build reference frames synthetically, so the
gap only surfaced on the first *real* backfill (M3.5). nba_api ships both tables as static
in-package data (zero network calls): team ids are franchise-stable, so the 30 current
franchises satisfy the FK for the whole PBP era, and the static player index covers every
historical player. Upserts are idempotent and cheap, so flows re-seed at every start — that's
also how newly-drafted players appear for the nightly ingest.
"""

import logging
from typing import Any

from nba_api.stats.static import players as static_players
from nba_api.stats.static import teams as static_teams
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.storage.models import Player, Team
from nbaforecast.storage.repositories import upsert_rows

logger = logging.getLogger(__name__)


def _team_rows() -> list[dict[str, Any]]:
    return [
        {
            "team_id": team["id"],
            "abbreviation": team["abbreviation"],
            "full_name": team["full_name"],
            "city": team["city"],
            "nickname": team["nickname"],
        }
        for team in static_teams.get_teams()
    ]


def _player_rows() -> list[dict[str, Any]]:
    return [
        {
            "player_id": player["id"],
            "full_name": player["full_name"],
            "first_name": player["first_name"],
            "last_name": player["last_name"],
        }
        for player in static_players.get_players()
    ]


async def seed_reference_tables(session: AsyncSession) -> tuple[int, int]:
    """Idempotently upsert all static teams and players; returns (teams, players) counts."""
    team_count = await upsert_rows(session, Team, _team_rows(), ("team_id",))
    player_count = await upsert_rows(session, Player, _player_rows(), ("player_id",))
    logger.info("seeded reference tables: %d teams, %d players", team_count, player_count)
    return team_count, player_count
