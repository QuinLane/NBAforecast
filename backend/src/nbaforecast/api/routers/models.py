"""Models router — champion provenance (backend-api.md §3)."""

import asyncio

from fastapi import APIRouter

from nbaforecast.api import services
from nbaforecast.api.schemas.models import ChampionProvenance

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/champions", response_model=list[ChampionProvenance])
async def list_champions() -> list[ChampionProvenance]:
    """Provenance for every head with a promoted champion (version, trained-through, features)."""
    # MLflow lookups are blocking — keep them off the event loop.
    return await asyncio.to_thread(services.models.champion_provenance)
