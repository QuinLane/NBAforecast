"""Teams service — backend-api.md §3 (Teams). Pure DB reads over the ``teams`` reference table."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import (
    HeadToHead,
    PlayerSummary,
    TeamProfile,
    TeamSummary,
)
from nbaforecast.api.services import games as games_service
from nbaforecast.storage.models import Game, Player, PlayerGameStats, Team

RECENT_GAMES = 10


def _to_summary(team: Team) -> TeamSummary:
    return TeamSummary(
        team_id=team.team_id,
        abbreviation=team.abbreviation,
        full_name=team.full_name,
        conference=team.conference,
        division=team.division,
    )


def _team_won(game: Game, team_id: int) -> bool | None:
    """Whether ``team_id`` won ``game``; ``None`` when the game has no final score."""
    if game.home_score is None or game.away_score is None:
        return None
    home_won = game.home_score > game.away_score
    return home_won if game.home_team_id == team_id else not home_won


async def _current_roster(
    session: AsyncSession, team_id: int, *, season: str | None
) -> list[Player]:
    """Players whose most recent game *in the team's current season* was for this team.

    Anchoring on each player's latest game (not "ever played for the team") keeps a mid-season
    trade on one roster only — the team they were last with — and scopes the roster to the
    current season so a full-era backfill doesn't list decades of alumni.
    """
    if season is None:
        return []
    # Rank each player's games in the season by recency; their rank-1 team is their current team.
    ranked = (
        select(
            PlayerGameStats.player_id.label("player_id"),
            PlayerGameStats.team_id.label("team_id"),
            func.row_number()
            .over(
                partition_by=PlayerGameStats.player_id,
                order_by=(Game.game_date.desc(), Game.game_id.desc()),
            )
            .label("rn"),
        )
        .join(Game, Game.game_id == PlayerGameStats.game_id)
        .where(Game.season == season)
        .subquery()
    )
    latest_team_is_this = select(ranked.c.player_id).where(
        ranked.c.rn == 1, ranked.c.team_id == team_id
    )
    return list(
        (
            await session.execute(
                select(Player)
                .where(Player.player_id.in_(latest_team_is_this))
                .order_by(Player.full_name)
            )
        )
        .scalars()
        .all()
    )


async def list_teams(
    session: AsyncSession, *, page: int = 1, page_size: int = 50
) -> Page[TeamSummary]:
    """``GET /teams`` — all teams (paginated, alphabetical)."""
    total = (await session.execute(select(func.count()).select_from(Team))).scalar_one()
    query = select(Team).order_by(Team.full_name).offset((page - 1) * page_size).limit(page_size)
    teams = (await session.execute(query)).scalars().all()
    return Page(
        items=[_to_summary(team) for team in teams], total=total, page=page, page_size=page_size
    )


async def get_team(session: AsyncSession, team_id: int) -> TeamSummary | None:
    """``GET /teams/{team_id}`` — one team, or ``None`` if it doesn't exist."""
    team = await session.get(Team, team_id)
    return None if team is None else _to_summary(team)


async def team_profile(
    session: AsyncSession, team_id: int, *, recent_limit: int = RECENT_GAMES
) -> TeamProfile | None:
    """``GET /teams/{team_id}/profile`` — record, roster, and recent games. ``None`` if unknown."""
    team = await session.get(Team, team_id)
    if team is None:
        return None

    team_games = (
        (
            await session.execute(
                select(Game)
                .where((Game.home_team_id == team_id) | (Game.away_team_id == team_id))
                .order_by(Game.game_date.desc())
            )
        )
        .scalars()
        .all()
    )

    wins = sum(1 for g in team_games if _team_won(g, team_id) is True)
    losses = sum(1 for g in team_games if _team_won(g, team_id) is False)

    roster_players = await _current_roster(
        session, team_id, season=team_games[0].season if team_games else None
    )
    roster = [
        PlayerSummary(
            player_id=p.player_id,
            full_name=p.full_name,
            position=p.position,
            is_active=p.is_active,
        )
        for p in roster_players
    ]

    recent = await games_service.summarize_games(session, list(team_games[:recent_limit]))
    return TeamProfile(
        team=_to_summary(team), wins=wins, losses=losses, roster=roster, recent_games=recent
    )


async def head_to_head(session: AsyncSession, team_id: int, opponent_id: int) -> HeadToHead | None:
    """``GET /teams/{team_id}/head-to-head?opponent=`` — the series between two teams.

    Returns ``None`` if either team is unknown. Only played (final-score) games count toward the
    record; the game list is most-recent-first so the frontend can lead with the last meeting.
    """
    team = await session.get(Team, team_id)
    opponent = await session.get(Team, opponent_id)
    if team is None or opponent is None:
        return None

    matchups = (
        (
            await session.execute(
                select(Game)
                .where(
                    ((Game.home_team_id == team_id) & (Game.away_team_id == opponent_id))
                    | ((Game.home_team_id == opponent_id) & (Game.away_team_id == team_id))
                )
                .order_by(Game.game_date.desc())
            )
        )
        .scalars()
        .all()
    )

    team_wins = sum(1 for g in matchups if _team_won(g, team_id) is True)
    opponent_wins = sum(1 for g in matchups if _team_won(g, team_id) is False)
    games = await games_service.summarize_games(session, list(matchups))
    return HeadToHead(
        team=_to_summary(team),
        opponent=_to_summary(opponent),
        team_wins=team_wins,
        opponent_wins=opponent_wins,
        games=games,
    )
