"""Pydantic request/response schemas for the public API contract."""

from nbaforecast.api.schemas.common import ErrorResponse, Page
from nbaforecast.api.schemas.games import GameDetail, GamePrediction, GameSummary, TeamSummary

__all__ = [
    "ErrorResponse",
    "GameDetail",
    "GamePrediction",
    "GameSummary",
    "Page",
    "TeamSummary",
]
