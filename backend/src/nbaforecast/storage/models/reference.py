"""Reference / dimension tables (``teams``, ``players``) — data-model §2."""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from nbaforecast.storage.database import Base
from nbaforecast.storage.models._mixins import TimestampMixin


class Team(TimestampMixin, Base):
    """One row per NBA team."""

    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    abbreviation: Mapped[str] = mapped_column(String(5), nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str | None] = mapped_column(String)
    nickname: Mapped[str | None] = mapped_column(String)
    conference: Mapped[str | None] = mapped_column(String)
    division: Mapped[str | None] = mapped_column(String)
    arena_name: Mapped[str | None] = mapped_column(String)
    arena_lat: Mapped[Decimal | None] = mapped_column(Numeric)
    arena_lon: Mapped[Decimal | None] = mapped_column(Numeric)


class Player(TimestampMixin, Base):
    """One row per NBA player."""

    __tablename__ = "players"

    player_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)
    position: Mapped[str | None] = mapped_column(String)
    height_inches: Mapped[int | None] = mapped_column(Integer)
    weight_lbs: Mapped[int | None] = mapped_column(Integer)
    birthdate: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
