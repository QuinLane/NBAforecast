"""Model-metadata response schemas — backend-api.md §3 (champion provenance)."""

from datetime import datetime

from pydantic import BaseModel


class ChampionProvenance(BaseModel):
    """Provenance for one head's current champion — the "how current is this model?" line.

    Surfaced in the UI next to predictions so every projection carries its own paper trail:
    which model version produced it, what season it was trained through, and the feature version.
    """

    head: str
    version: str  # short MLflow run id
    feature_version: str | None
    trained_through_season: str | None  # e.g. "2025-26"
    trained_at: datetime | None
