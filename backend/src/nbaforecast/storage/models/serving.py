"""Model / serving tables — data-model §5.

RAPM snapshots, persisted served predictions, the live win-prob timeline, and the ingestion
checkpoint that lets backfill resume after a crash.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nbaforecast.storage.database import Base
from nbaforecast.storage.models._mixins import CreatedAtMixin


class PlayerRapm(CreatedAtMixin, Base):
    """RAPM snapshot per player — PK (player_id, as_of_date, window)."""

    __tablename__ = "player_rapm"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.player_id"), primary_key=True, index=True
    )
    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    window: Mapped[int] = mapped_column(Integer, primary_key=True)
    orapm: Mapped[Decimal | None] = mapped_column(Numeric)
    drapm: Mapped[Decimal | None] = mapped_column(Numeric)
    rapm: Mapped[Decimal | None] = mapped_column(Numeric)
    possessions: Mapped[int | None] = mapped_column(Integer)


class Prediction(CreatedAtMixin, Base):
    """A served prediction, persisted for accuracy tracking + the v2 market benchmark."""

    __tablename__ = "predictions"

    prediction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("games.game_id"), nullable=False, index=True
    )
    player_id: Mapped[int | None] = mapped_column(BigInteger)
    head: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    interval_low: Mapped[Decimal | None] = mapped_column(Numeric)
    interval_high: Mapped[Decimal | None] = mapped_column(Numeric)
    market: Mapped[Decimal | None] = mapped_column(Numeric)
    mlflow_run_id: Mapped[str] = mapped_column(String, nullable=False)
    feature_version: Mapped[str] = mapped_column(String, nullable=False)
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class LiveWinProbTimeline(CreatedAtMixin, Base):
    """Per-event win-probability timeline powering the post-game replay chart."""

    __tablename__ = "live_win_prob_timeline"

    game_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("games.game_id"), primary_key=True, index=True
    )
    event_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    seconds_remaining_game: Mapped[int] = mapped_column(Integer, nullable=False)
    score_diff: Mapped[int] = mapped_column(Integer, nullable=False)
    win_prob: Mapped[Decimal] = mapped_column(Numeric, nullable=False)


class IngestedGame(Base):
    """Ingestion checkpoint — which parts of each game are loaded (resumable backfill)."""

    __tablename__ = "ingested_games"

    game_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    entities_done: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
