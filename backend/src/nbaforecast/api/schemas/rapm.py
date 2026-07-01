"""RAPM response schemas — backend-api.md §4 (``RapmEntry``)."""

from datetime import date

from pydantic import BaseModel


class RapmEntry(BaseModel):
    """One leaderboard row — a player's RAPM from a single snapshot (backend-api.md §4)."""

    player_id: int
    full_name: str | None
    as_of_date: date
    window: int
    orapm: float | None
    drapm: float | None
    rapm: float | None
    possessions: int | None


class RapmHistoryEntry(BaseModel):
    """One point in a player's RAPM history — ``GET /players/{player_id}/rapm``."""

    as_of_date: date
    window: int
    orapm: float | None
    drapm: float | None
    rapm: float | None
    possessions: int | None
