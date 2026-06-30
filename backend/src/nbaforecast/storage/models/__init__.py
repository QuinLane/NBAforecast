"""SQLAlchemy 2.0 ORM models — the canonical realization of data-model.md §§2,3,4,5.

Importing this package registers every table on ``Base.metadata`` so Alembic and the
schema-match test see the full schema.
"""

from nbaforecast.storage.database import Base
from nbaforecast.storage.models.gold import FeatureGameState, FeaturePlayerGame, FeatureTeamGame
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
    "FeatureGameState",
    "FeaturePlayerGame",
    "FeatureTeamGame",
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
