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


# Home-city coordinates per franchise (city-center approximations — the travel-distance and
# timezone features operate at flight scale, where ±20 km is noise). nba_api's static data
# carries no coordinates, so these are maintained here.
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "ATL": (33.75, -84.39),
    "BOS": (42.36, -71.06),
    "BKN": (40.68, -73.97),
    "CHA": (35.23, -80.84),
    "CHI": (41.88, -87.63),
    "CLE": (41.50, -81.69),
    "DAL": (32.78, -96.80),
    "DEN": (39.74, -104.99),
    "DET": (42.33, -83.05),
    "GSW": (37.77, -122.42),
    "HOU": (29.76, -95.37),
    "IND": (39.77, -86.16),
    "LAC": (34.05, -118.24),
    "LAL": (34.05, -118.24),
    "MEM": (35.15, -90.05),
    "MIA": (25.76, -80.19),
    "MIL": (43.04, -87.91),
    "MIN": (44.98, -93.27),
    "NOP": (29.95, -90.07),
    "NYK": (40.75, -73.99),
    "OKC": (35.47, -97.52),
    "ORL": (28.54, -81.38),
    "PHI": (39.95, -75.17),
    "PHX": (33.45, -112.07),
    "POR": (45.52, -122.68),
    "SAC": (38.58, -121.49),
    "SAS": (29.42, -98.49),
    "TOR": (43.65, -79.38),
    "UTA": (40.76, -111.89),
    "WAS": (38.90, -77.04),
}


def _team_rows() -> list[dict[str, Any]]:
    rows = []
    for team in static_teams.get_teams():
        lat, lon = _CITY_COORDS.get(team["abbreviation"], (None, None))
        rows.append(
            {
                "team_id": team["id"],
                "abbreviation": team["abbreviation"],
                "full_name": team["full_name"],
                "city": team["city"],
                "nickname": team["nickname"],
                "arena_lat": lat,
                "arena_lon": lon,
            }
        )
    return rows


def _player_rows() -> list[dict[str, Any]]:
    return [
        {
            "player_id": player["id"],
            "full_name": player["full_name"],
            "first_name": player["first_name"],
            "last_name": player["last_name"],
            "is_active": bool(player.get("is_active", False)),
        }
        for player in static_players.get_players()
    ]


async def seed_reference_tables(session: AsyncSession) -> tuple[int, int]:
    """Idempotently upsert all static teams and players; returns (teams, players) counts."""
    team_count = await upsert_rows(session, Team, _team_rows(), ("team_id",))
    player_count = await upsert_rows(session, Player, _player_rows(), ("player_id",))
    logger.info("seeded reference tables: %d teams, %d players", team_count, player_count)
    return team_count, player_count


def _players_from_v3_boxscore(boxscore_raw: dict[str, Any]) -> list[dict[str, Any]]:
    root = boxscore_raw["traditional"]["boxScoreTraditional"]
    rows: list[dict[str, Any]] = []
    for side in ("homeTeam", "awayTeam"):
        for player in root[side].get("players", []):
            first = player.get("firstName") or None
            last = player.get("familyName") or None
            full = " ".join(part for part in (first, last) if part)
            rows.append(
                {
                    "player_id": int(player["personId"]),
                    "full_name": full or str(player["personId"]),
                    "first_name": first,
                    "last_name": last,
                }
            )
    return rows


async def ensure_players_from_boxscore(session: AsyncSession, boxscore_raw: dict[str, Any]) -> int:
    """Upsert every player appearing in a v3 boxscore into ``players``.

    The static index (:func:`seed_reference_tables`) is frozen at nba_api's release date, so
    players who debuted after it (rookies, two-way signings) FK-violate
    ``player_game_stats`` — found live at M3.5 with 2025-26 rookies. The boxscore itself is
    the authoritative roster source, so seeding from it is self-healing for any era.
    """
    return await upsert_rows(
        session, Player, _players_from_v3_boxscore(boxscore_raw), ("player_id",)
    )
