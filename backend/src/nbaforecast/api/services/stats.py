"""Stats-hub leaderboards service — backend-api.md §3 (Stats hub) + Prompt 5.

Generic per-player season leaderboards: the average of a counting stat across a season's games,
computed straight off ``player_game_stats``. Kept deliberately simple (a DB aggregate, no model)
— the "interesting" leaderboards (RAPM) have their own endpoint.
"""

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import LeaderboardEntry
from nbaforecast.storage.models import Game, Player, PlayerGameStats

# Stat name → the column averaged. Whitelisted so ``stat`` can't select an arbitrary attribute.
LEADERBOARD_STATS = {
    "pts": PlayerGameStats.pts,
    "reb": PlayerGameStats.reb,
    "ast": PlayerGameStats.ast,
    "stl": PlayerGameStats.stl,
    "blk": PlayerGameStats.blk,
    "fg3m": PlayerGameStats.fg3m,
}


async def leaderboard(
    session: AsyncSession,
    *,
    stat: str,
    season: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> Page[LeaderboardEntry]:
    """``GET /stats/leaderboards`` — players ranked by per-game average of ``stat``.

    Raises ``KeyError`` for an unknown ``stat`` (router → 400).
    """
    if stat not in LEADERBOARD_STATS:
        raise KeyError(stat)
    column = LEADERBOARD_STATS[stat]

    value = func.avg(column)
    games_played = func.count(cast(1, Integer))
    base = (
        select(
            PlayerGameStats.player_id,
            Player.full_name,
            value.label("value"),
            games_played.label("games_played"),
        )
        .join(Player, Player.player_id == PlayerGameStats.player_id, isouter=True)
        .join(Game, Game.game_id == PlayerGameStats.game_id)
        .group_by(PlayerGameStats.player_id, Player.full_name)
    )
    if season is not None:
        base = base.where(Game.season == season)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    paged = base.order_by(value.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(paged)).all()
    items = [
        LeaderboardEntry(
            player_id=row.player_id,
            full_name=row.full_name,
            stat=stat,
            value=float(row.value),
            games_played=row.games_played,
        )
        for row in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)
