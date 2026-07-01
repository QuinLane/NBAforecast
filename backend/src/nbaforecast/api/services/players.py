"""Players service — backend-api.md §3 (Teams & players) + Prompt 5.

Profile/list/game-log/shot-chart reads are pure DB queries; the props projection path
(``player_props``) mirrors ``services/games.py``'s prediction path but over
``features_player_game`` and the props champion heads.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import (
    PlayerDetail,
    PlayerGameLog,
    PlayerSummary,
    ShotChartEntry,
)
from nbaforecast.storage.models import Game, Player, PlayerGameStats, Shot

RECENT_GAMES = 10


def _to_summary(player: Player) -> PlayerSummary:
    return PlayerSummary(
        player_id=player.player_id,
        full_name=player.full_name,
        position=player.position,
        is_active=player.is_active,
    )


async def list_players(
    session: AsyncSession,
    *,
    active: bool | None = None,
    page: int = 1,
    page_size: int = 25,
) -> Page[PlayerSummary]:
    """``GET /players`` — paginated player list, optionally filtered to active players."""
    query = select(Player)
    if active is not None:
        query = query.where(Player.is_active == active)
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    paged = query.order_by(Player.full_name).offset((page - 1) * page_size).limit(page_size)
    players = (await session.execute(paged)).scalars().all()
    return Page(
        items=[_to_summary(p) for p in players], total=total, page=page, page_size=page_size
    )


async def get_player(session: AsyncSession, player_id: int) -> PlayerDetail | None:
    """``GET /players/{player_id}`` — profile + the player's most recent game logs."""
    player = await session.get(Player, player_id)
    if player is None:
        return None

    query = (
        select(PlayerGameStats, Game.game_date)
        .join(Game, Game.game_id == PlayerGameStats.game_id)
        .where(PlayerGameStats.player_id == player_id)
        .order_by(Game.game_date.desc())
        .limit(RECENT_GAMES)
    )
    rows = (await session.execute(query)).all()
    recent = [
        PlayerGameLog(
            game_id=stat.game_id,
            game_date=game_date,
            team_id=stat.team_id,
            opponent_team_id=stat.opponent_team_id,
            is_home=stat.is_home,
            min=None if stat.min is None else float(stat.min),
            pts=stat.pts,
            reb=stat.reb,
            ast=stat.ast,
            fg3m=stat.fg3m,
        )
        for stat, game_date in rows
    ]
    return PlayerDetail(
        **_to_summary(player).model_dump(),
        height_inches=player.height_inches,
        weight_lbs=player.weight_lbs,
        birthdate=player.birthdate,
        recent_games=recent,
    )


async def player_shots(
    session: AsyncSession, player_id: int, *, season: str | None = None
) -> list[ShotChartEntry]:
    """``GET /players/{player_id}/shots`` — the player's field-goal attempts (optionally one
    season), for the shot chart. Carries ``location_reliable`` so the frontend can drop
    spatially-unreliable attempts from the chart while still counting them in totals."""
    query = select(Shot).where(Shot.player_id == player_id)
    if season is not None:
        query = query.join(Game, Game.game_id == Shot.game_id).where(Game.season == season)
    shots = (await session.execute(query.order_by(Shot.game_id, Shot.event_num))).scalars().all()
    return [
        ShotChartEntry(
            game_id=shot.game_id,
            period=shot.period,
            loc_x=shot.loc_x,
            loc_y=shot.loc_y,
            shot_distance=shot.shot_distance,
            shot_zone=shot.shot_zone,
            shot_type=shot.shot_type,
            made=shot.made,
            location_reliable=shot.location_reliable,
        )
        for shot in shots
    ]
