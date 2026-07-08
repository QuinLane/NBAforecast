"""Players service — backend-api.md §3 (Teams & players) + Prompt 5.

Profile/list/game-log/shot-chart reads are pure DB queries; the props projection path
(``player_props``) mirrors ``services/games.py``'s prediction path but over
``features_player_game`` and the props champion heads.
"""

from collections import OrderedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import (
    PlayerDetail,
    PlayerGameLog,
    PlayerGameStatLine,
    PlayerSeasonAverages,
    PlayerStatTrajectory,
    PlayerSummary,
    ShotChartEntry,
)
from nbaforecast.storage.models import Game, Player, PlayerGameStats, Shot, Team

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
    with_stats: bool = False,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> Page[PlayerSummary]:
    """``GET /players`` — paginated player list, optionally filtered.

    ``with_stats`` keeps only players with at least one ingested game line — the reference
    table carries the full historical index (~5k players), most of whom have no data in the
    loaded seasons (walkthrough finding, T3.15). ``search`` is a case-insensitive name substring
    (powers the header quick-search).
    """
    query = select(Player)
    if active is not None:
        query = query.where(Player.is_active == active)
    if with_stats:
        query = query.where(
            select(PlayerGameStats.player_id)
            .where(PlayerGameStats.player_id == Player.player_id)
            .exists()
        )
    if search:
        query = query.where(Player.full_name.ilike(f"%{search}%"))
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
        select(PlayerGameStats, Game)
        .join(Game, Game.game_id == PlayerGameStats.game_id)
        .where(PlayerGameStats.player_id == player_id)
        .order_by(Game.game_date.desc())
        .limit(RECENT_GAMES)
    )
    rows = (await session.execute(query)).all()
    abbreviations = {
        team.team_id: team.abbreviation
        for team in (await session.execute(select(Team))).scalars().all()
    }
    recent = []
    for stat, game in rows:
        won: bool | None = None
        if game.home_score is not None and game.away_score is not None:
            home_won = game.home_score > game.away_score
            won = home_won if stat.is_home else not home_won
        recent.append(
            PlayerGameLog(
                game_id=stat.game_id,
                game_date=game.game_date,
                team_id=stat.team_id,
                opponent_team_id=stat.opponent_team_id,
                team_abbreviation=abbreviations.get(stat.team_id),
                opponent_abbreviation=abbreviations.get(stat.opponent_team_id),
                is_home=stat.is_home,
                won=won,
                min=None if stat.min is None else float(stat.min),
                pts=stat.pts,
                reb=stat.reb,
                ast=stat.ast,
                fg3m=stat.fg3m,
            )
        )
    return PlayerDetail(
        **_to_summary(player).model_dump(),
        height_inches=player.height_inches,
        weight_lbs=player.weight_lbs,
        birthdate=player.birthdate,
        recent_games=recent,
    )


class _SeasonAcc:
    """Running totals for one season, turned into per-game averages at the end."""

    def __init__(self) -> None:
        self.games = 0
        self.min_sum = 0.0
        self.min_games = 0  # games with a recorded minutes value
        self.pts = self.reb = self.ast = self.fg3m = 0
        self.fgm = self.fga = self.fg3a = self.ftm = self.fta = 0

    def add(self, stat: PlayerGameStats) -> None:
        self.games += 1
        if stat.min is not None:
            self.min_sum += float(stat.min)
            self.min_games += 1
        self.pts += stat.pts
        self.reb += stat.reb
        self.ast += stat.ast
        self.fg3m += stat.fg3m
        self.fgm += stat.fgm
        self.fga += stat.fga
        self.fg3a += stat.fg3a
        self.ftm += stat.ftm
        self.fta += stat.fta


def _pct(makes: int, attempts: int) -> float | None:
    return None if attempts == 0 else round(makes / attempts, 4)


def _season_averages(season: str, acc: _SeasonAcc) -> PlayerSeasonAverages:
    games = acc.games
    return PlayerSeasonAverages(
        season=season,
        games_played=games,
        min=None if acc.min_games == 0 else round(acc.min_sum / acc.min_games, 1),
        pts=round(acc.pts / games, 1),
        reb=round(acc.reb / games, 1),
        ast=round(acc.ast / games, 1),
        fg3m=round(acc.fg3m / games, 1),
        fg_pct=_pct(acc.fgm, acc.fga),
        fg3_pct=_pct(acc.fg3m, acc.fg3a),
        ft_pct=_pct(acc.ftm, acc.fta),
    )


async def player_stat_trajectory(
    session: AsyncSession, player_id: int
) -> PlayerStatTrajectory | None:
    """``GET /players/{player_id}/stats`` — chronological per-game lines + season averages.

    Returns ``None`` for an unknown player (404). A known player with no ingested games yields
    empty ``games``/``seasons`` (the profile page renders its own empty state). Seasons are
    ordered chronologically (rows arrive by game date, so first-seen season order is correct).
    """
    player = await session.get(Player, player_id)
    if player is None:
        return None

    query = (
        select(PlayerGameStats, Game.game_date, Game.season)
        .join(Game, Game.game_id == PlayerGameStats.game_id)
        .where(PlayerGameStats.player_id == player_id)
        .order_by(Game.game_date)
    )
    rows = (await session.execute(query)).all()

    games = [
        PlayerGameStatLine(
            game_id=stat.game_id,
            game_date=game_date,
            season=season,
            min=None if stat.min is None else float(stat.min),
            pts=stat.pts,
            reb=stat.reb,
            ast=stat.ast,
            fg3m=stat.fg3m,
        )
        for stat, game_date, season in rows
    ]

    accs: OrderedDict[str, _SeasonAcc] = OrderedDict()
    for stat, _game_date, season in rows:
        accs.setdefault(season, _SeasonAcc()).add(stat)
    seasons = [_season_averages(season, acc) for season, acc in accs.items()]

    return PlayerStatTrajectory(games=games, seasons=seasons)


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
