"""Players router — backend-api.md §3 (Teams & players, RAPM history) + Prompt 5."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api import services
from nbaforecast.api.deps import get_db_session, get_model_provider
from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.players import (
    PlayerDetail,
    PlayerStatTrajectory,
    PlayerSummary,
    PropsProjection,
    ShotChartEntry,
)
from nbaforecast.api.schemas.rapm import RapmHistoryEntry

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=Page[PlayerSummary])
async def list_players(
    active: bool | None = None,
    with_stats: bool = False,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    session: AsyncSession = Depends(get_db_session),
) -> Page[PlayerSummary]:
    return await services.players.list_players(
        session,
        active=active,
        with_stats=with_stats,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/{player_id}", response_model=PlayerDetail)
async def get_player(
    player_id: int, session: AsyncSession = Depends(get_db_session)
) -> PlayerDetail:
    player = await services.players.get_player(session, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"player {player_id} not found")
    return player


@router.get("/{player_id}/stats", response_model=PlayerStatTrajectory)
async def get_player_stats(
    player_id: int, session: AsyncSession = Depends(get_db_session)
) -> PlayerStatTrajectory:
    trajectory = await services.players.player_stat_trajectory(session, player_id)
    if trajectory is None:
        raise HTTPException(status_code=404, detail=f"player {player_id} not found")
    return trajectory


@router.get("/{player_id}/shots", response_model=list[ShotChartEntry])
async def get_player_shots(
    player_id: int,
    season: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[ShotChartEntry]:
    return await services.players.player_shots(session, player_id, season=season)


@router.get("/{player_id}/rapm", response_model=list[RapmHistoryEntry])
async def get_player_rapm(
    player_id: int,
    window: int = services.rapm.DEFAULT_WINDOW,
    session: AsyncSession = Depends(get_db_session),
) -> list[RapmHistoryEntry]:
    return await services.rapm.player_rapm_history(session, player_id, window=window)


@router.get("/{player_id}/props", response_model=list[PropsProjection])
async def get_player_props(
    player_id: int,
    game_id: str,
    full: bool = False,
    session: AsyncSession = Depends(get_db_session),
    model_provider: ModelProvider = Depends(get_model_provider),
) -> list[PropsProjection]:
    try:
        projections = await services.props.player_props(
            session, model_provider, player_id, game_id, full=full
        )
    except RuntimeError as exc:
        # No props champion loaded yet (transient MLflow/startup state) — mirror games' 503.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if projections is None:
        raise HTTPException(
            status_code=404,
            detail=f"no props available for player {player_id} in game {game_id!r}",
        )
    return projections
