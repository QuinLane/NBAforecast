"""Teams service — backend-api.md §3 (Teams). Pure DB reads over the ``teams`` reference table."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import TeamSummary
from nbaforecast.storage.models import Team


def _to_summary(team: Team) -> TeamSummary:
    return TeamSummary(
        team_id=team.team_id,
        abbreviation=team.abbreviation,
        full_name=team.full_name,
        conference=team.conference,
        division=team.division,
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
