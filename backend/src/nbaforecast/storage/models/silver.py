"""Core silver tables — data-model §3.

Parsed, validated, deduped rows: one row per real-world entity. Large tables
(``play_by_play``, ``shots``, ``possessions``) are Parquet-primary but kept here in Postgres
for serving (shot charts, replay, etc.).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from nbaforecast.storage.database import Base
from nbaforecast.storage.models._mixins import CreatedAtMixin, TimestampMixin


class Game(TimestampMixin, Base):
    """One row per game. ``game_id`` is the NBA string id (leading zeros preserved)."""

    __tablename__ = "games"
    __table_args__ = (CheckConstraint("home_team_id <> away_team_id", name="home_away_distinct"),)

    game_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    season: Mapped[str] = mapped_column(String(7), nullable=False)
    season_start_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season_type: Mapped[str] = mapped_column(String, nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    game_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.team_id"), nullable=False, index=True
    )
    away_team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.team_id"), nullable=False, index=True
    )
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False)
    num_periods: Mapped[int] = mapped_column(Integer, nullable=False, default=4)


class TeamGameStats(TimestampMixin, Base):
    """Team box-score line for a game — PK (game_id, team_id)."""

    __tablename__ = "team_game_stats"

    game_id: Mapped[str] = mapped_column(String(20), ForeignKey("games.game_id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.team_id"), primary_key=True, index=True
    )
    opponent_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)

    pts: Mapped[int] = mapped_column(Integer, nullable=False)
    reb: Mapped[int] = mapped_column(Integer, nullable=False)
    oreb: Mapped[int] = mapped_column(Integer, nullable=False)
    dreb: Mapped[int] = mapped_column(Integer, nullable=False)
    ast: Mapped[int] = mapped_column(Integer, nullable=False)
    stl: Mapped[int] = mapped_column(Integer, nullable=False)
    blk: Mapped[int] = mapped_column(Integer, nullable=False)
    tov: Mapped[int] = mapped_column(Integer, nullable=False)
    pf: Mapped[int] = mapped_column(Integer, nullable=False)

    fgm: Mapped[int] = mapped_column(Integer, nullable=False)
    fga: Mapped[int] = mapped_column(Integer, nullable=False)
    fg3m: Mapped[int] = mapped_column(Integer, nullable=False)
    fg3a: Mapped[int] = mapped_column(Integer, nullable=False)
    ftm: Mapped[int] = mapped_column(Integer, nullable=False)
    fta: Mapped[int] = mapped_column(Integer, nullable=False)

    off_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    def_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    net_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    pace: Mapped[Decimal | None] = mapped_column(Numeric)
    possessions: Mapped[Decimal | None] = mapped_column(Numeric)


class PlayerGameStats(TimestampMixin, Base):
    """Player box-score line for a game — PK (game_id, player_id)."""

    __tablename__ = "player_game_stats"

    game_id: Mapped[str] = mapped_column(String(20), ForeignKey("games.game_id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.player_id"), primary_key=True, index=True
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    opponent_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False)

    min: Mapped[Decimal | None] = mapped_column(Numeric)
    pts: Mapped[int] = mapped_column(Integer, nullable=False)
    reb: Mapped[int] = mapped_column(Integer, nullable=False)
    oreb: Mapped[int] = mapped_column(Integer, nullable=False)
    dreb: Mapped[int] = mapped_column(Integer, nullable=False)
    ast: Mapped[int] = mapped_column(Integer, nullable=False)
    stl: Mapped[int] = mapped_column(Integer, nullable=False)
    blk: Mapped[int] = mapped_column(Integer, nullable=False)
    tov: Mapped[int] = mapped_column(Integer, nullable=False)
    pf: Mapped[int] = mapped_column(Integer, nullable=False)

    fgm: Mapped[int] = mapped_column(Integer, nullable=False)
    fga: Mapped[int] = mapped_column(Integer, nullable=False)
    fg3m: Mapped[int] = mapped_column(Integer, nullable=False)
    fg3a: Mapped[int] = mapped_column(Integer, nullable=False)
    ftm: Mapped[int] = mapped_column(Integer, nullable=False)
    fta: Mapped[int] = mapped_column(Integer, nullable=False)

    plus_minus: Mapped[int | None] = mapped_column(Integer)
    usage_rate: Mapped[Decimal | None] = mapped_column(Numeric)


class PlayByPlay(CreatedAtMixin, Base):
    """One row per play-by-play event — PK (game_id, event_num)."""

    __tablename__ = "play_by_play"
    __table_args__ = (Index("ix_play_by_play_game_id_period", "game_id", "period"),)

    game_id: Mapped[str] = mapped_column(String(20), ForeignKey("games.game_id"), primary_key=True)
    event_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    pc_time: Mapped[str | None] = mapped_column(String)
    seconds_remaining_period: Mapped[int | None] = mapped_column(Integer)
    event_msg_type: Mapped[int | None] = mapped_column(Integer)
    event_action_type: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    player1_id: Mapped[int | None] = mapped_column(BigInteger)
    player2_id: Mapped[int | None] = mapped_column(BigInteger)
    player3_id: Mapped[int | None] = mapped_column(BigInteger)
    team_id: Mapped[int | None] = mapped_column(BigInteger)


class Shot(CreatedAtMixin, Base):
    """One row per field-goal attempt — surrogate PK + UNIQUE(game_id, event_num)."""

    __tablename__ = "shots"
    __table_args__ = (UniqueConstraint("game_id", "event_num"),)

    shot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("games.game_id"), nullable=False, index=True
    )
    event_num: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.player_id"), nullable=False, index=True
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    seconds_remaining_period: Mapped[int | None] = mapped_column(Integer)
    loc_x: Mapped[int | None] = mapped_column(Integer)
    loc_y: Mapped[int | None] = mapped_column(Integer)
    shot_distance: Mapped[int | None] = mapped_column(Integer)
    shot_zone: Mapped[str | None] = mapped_column(String, index=True)
    shot_zone_area: Mapped[str | None] = mapped_column(String)
    shot_zone_range: Mapped[str | None] = mapped_column(String)
    shot_type: Mapped[str | None] = mapped_column(String)
    action_type: Mapped[str | None] = mapped_column(String)
    made: Mapped[bool] = mapped_column(Boolean, nullable=False)
    location_reliable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Possession(CreatedAtMixin, Base):
    """One row per possession with on-court lineups — surrogate PK. Substrate for RAPM."""

    __tablename__ = "possessions"

    possession_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("games.game_id"), nullable=False, index=True
    )
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[int | None] = mapped_column(Integer)
    end_seconds: Mapped[int | None] = mapped_column(Integer)
    offense_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    defense_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    off_player_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False)
    def_player_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False)
