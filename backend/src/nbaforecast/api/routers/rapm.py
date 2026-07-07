"""RAPM router — backend-api.md §3 (RAPM leaderboard) + Prompt 5."""

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api import services
from nbaforecast.api.deps import get_db_session
from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.rapm import RapmEntry

router = APIRouter(prefix="/rapm", tags=["rapm"])


@router.get("", response_model=Page[RapmEntry])
async def rapm_leaderboard(
    window: int = services.rapm.DEFAULT_WINDOW,
    as_of: date_type | None = None,
    sort: str = "rapm",
    min_poss: int = services.rapm.DEFAULT_MIN_POSS,
    page: int = 1,
    page_size: int = 25,
    session: AsyncSession = Depends(get_db_session),
) -> Page[RapmEntry]:
    try:
        return await services.rapm.rapm_leaderboard(
            session,
            window=window,
            as_of=as_of,
            sort=sort,
            min_poss=min_poss,
            page=page,
            page_size=page_size,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid sort {sort!r}; choose one of {sorted(services.rapm.SORTABLE_COLUMNS)}",
        ) from exc
