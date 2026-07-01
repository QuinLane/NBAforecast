"""Teams router — backend-api.md §3 (Teams) + Prompt 5."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api import services
from nbaforecast.api.deps import get_db_session
from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import TeamSummary

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=Page[TeamSummary])
async def list_teams(
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> Page[TeamSummary]:
    return await services.teams.list_teams(session, page=page, page_size=page_size)


@router.get("/{team_id}", response_model=TeamSummary)
async def get_team(team_id: int, session: AsyncSession = Depends(get_db_session)) -> TeamSummary:
    team = await services.teams.get_team(session, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"team {team_id} not found")
    return team
