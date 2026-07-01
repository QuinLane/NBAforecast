"""Stats router — backend-api.md §3 (Stats hub leaderboards) + Prompt 5."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api import services
from nbaforecast.api.deps import get_db_session
from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import LeaderboardEntry

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/leaderboards", response_model=Page[LeaderboardEntry])
async def leaderboards(
    stat: str,
    season: str | None = None,
    page: int = 1,
    page_size: int = 25,
    session: AsyncSession = Depends(get_db_session),
) -> Page[LeaderboardEntry]:
    try:
        return await services.stats.leaderboard(
            session, stat=stat, season=season, page=page, page_size=page_size
        )
    except KeyError as exc:
        valid = sorted(services.stats.LEADERBOARD_STATS)
        raise HTTPException(
            status_code=400, detail=f"invalid stat {stat!r}; choose one of {valid}"
        ) from exc
