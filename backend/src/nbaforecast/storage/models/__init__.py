"""SQLAlchemy 2.0 ORM models — the canonical realization of data-model.md §§2,3,5.

Importing this package registers every table on ``Base.metadata`` so Alembic and the
schema-match test see the full schema. Gold ``features_*`` tables (data-model §4) are created
later by T2.3 (feature-engineering Prompt 5), where their columns are finalized.
"""

from nbaforecast.storage.database import Base
from nbaforecast.storage.models.reference import Player, Team
from nbaforecast.storage.models.serving import (
    IngestedGame,
    LiveWinProbTimeline,
    PlayerRapm,
    Prediction,
)
from nbaforecast.storage.models.silver import (
    Game,
    PlayByPlay,
    PlayerGameStats,
    Possession,
    Shot,
    TeamGameStats,
)

__all__ = [
    "Base",
    "Game",
    "IngestedGame",
    "LiveWinProbTimeline",
    "PlayByPlay",
    "Player",
    "PlayerGameStats",
    "PlayerRapm",
    "Possession",
    "Prediction",
    "Shot",
    "Team",
    "TeamGameStats",
]
