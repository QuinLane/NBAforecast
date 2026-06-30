"""Games + predictions router — backend-api.md §3 + Prompt 4."""

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api import services
from nbaforecast.api.deps import get_db_session, get_model_provider
from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.api.schemas.common import Page
from nbaforecast.api.schemas.games import GameDetail, GamePrediction, GameSummary

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=Page[GameSummary])
async def list_games(
    game_date: date_type | None = None,
    season: str | None = None,
    team: int | None = None,
    page: int = 1,
    page_size: int = 25,
    session: AsyncSession = Depends(get_db_session),
) -> Page[GameSummary]:
    return await services.games.list_games(
        session, game_date=game_date, season=season, team_id=team, page=page, page_size=page_size
    )


@router.get("/{game_id}", response_model=GameDetail)
async def get_game(game_id: str, session: AsyncSession = Depends(get_db_session)) -> GameDetail:
    game = await services.games.get_game(session, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail=f"game {game_id!r} not found")
    return game


async def _predict_or_404(
    session: AsyncSession, model_provider: ModelProvider, game_id: str, *, full: bool
) -> GamePrediction:
    try:
        prediction = await services.games.get_game_prediction(
            session, model_provider, game_id, full=full
        )
    except RuntimeError as exc:
        # ModelProvider.get() raises this when no champion has been loaded yet — a transient
        # startup/MLflow-outage state, not a client error.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"no prediction available for game {game_id!r}")
    return prediction


@router.get("/{game_id}/prediction", response_model=GamePrediction)
async def get_game_prediction(
    game_id: str,
    session: AsyncSession = Depends(get_db_session),
    model_provider: ModelProvider = Depends(get_model_provider),
) -> GamePrediction:
    return await _predict_or_404(session, model_provider, game_id, full=False)


@router.get("/{game_id}/prediction/full-explanation", response_model=GamePrediction)
async def get_game_prediction_full_explanation(
    game_id: str,
    session: AsyncSession = Depends(get_db_session),
    model_provider: ModelProvider = Depends(get_model_provider),
) -> GamePrediction:
    return await _predict_or_404(session, model_provider, game_id, full=True)
