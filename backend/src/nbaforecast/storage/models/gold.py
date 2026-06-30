"""Gold / feature tables — data-model.md §4. Created in T2.3 (feature-engineering Prompt 5).

``FeatureTeamGame`` is populated now by ``features/team_game.py`` (T2.2) via the materializer in
``features/materialize.py``. ``FeaturePlayerGame`` and ``FeatureGameState`` are scaffolded here
ahead of their builders (``features/player_game.py`` T3.2, ``features/game_state.py`` T4.1) so the
full gold schema exists in one migration; they stay empty until those tasks land.

Every gold table carries ``feature_version`` (which run of the relevant ``build_*`` function
produced the row) and ``created_at`` so a model's training run can always be traced back to the
exact feature definitions it saw.
"""

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from nbaforecast.storage.database import Base
from nbaforecast.storage.models._mixins import CreatedAtMixin


class FeatureTeamGame(CreatedAtMixin, Base):
    """Team-game feature row — PK (game_id, team_id). feature-engineering.md §4."""

    __tablename__ = "features_team_game"

    game_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("games.game_id"), primary_key=True, index=True
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.team_id"), primary_key=True, index=True
    )
    opponent_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season: Mapped[str] = mapped_column(String(7), nullable=False)
    season_start_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)

    days_rest: Mapped[Decimal | None] = mapped_column(Numeric)
    # 0/1 float (not Boolean) — NaN-capable for a team's first-ever game, fed straight to models.
    is_back_to_back: Mapped[Decimal | None] = mapped_column(Numeric)
    games_last_7d: Mapped[int | None] = mapped_column(Integer)
    games_last_14d: Mapped[int | None] = mapped_column(Integer)
    travel_distance_km: Mapped[Decimal | None] = mapped_column(Numeric)
    tz_shift: Mapped[Decimal | None] = mapped_column(Numeric)

    roll5_net_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_net_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    roll5_off_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_off_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    roll5_def_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_def_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    roll5_pace: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_pace: Mapped[Decimal | None] = mapped_column(Numeric)

    season_off_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    season_def_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    season_net_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    season_pace: Mapped[Decimal | None] = mapped_column(Numeric)
    win_pct_to_date: Mapped[Decimal | None] = mapped_column(Numeric)

    elo: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    opp_adj_net_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    h2h_record: Mapped[Decimal | None] = mapped_column(Numeric)
    h2h_avg_margin: Mapped[Decimal | None] = mapped_column(Numeric)
    rest_advantage: Mapped[Decimal | None] = mapped_column(Numeric)
    rating_diff: Mapped[Decimal | None] = mapped_column(Numeric)
    elo_diff: Mapped[Decimal | None] = mapped_column(Numeric)

    # From RAPM snapshots (rapm.md) — NULL until T3.9 wires player_rapm into team features.
    team_orapm: Mapped[Decimal | None] = mapped_column(Numeric)
    team_drapm: Mapped[Decimal | None] = mapped_column(Numeric)

    feature_version: Mapped[str] = mapped_column(String, nullable=False)


class FeaturePlayerGame(CreatedAtMixin, Base):
    """Player-game feature row — PK (game_id, player_id). Populated starting T3.2.

    feature-engineering.md §4 (player-game): recent production (rolling mean/std of
    pts/reb/ast/fg3m), role/usage, season-to-date averages, and matchup/opponent context.
    """

    __tablename__ = "features_player_game"

    game_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("games.game_id"), primary_key=True, index=True
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.player_id"), primary_key=True, index=True
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opponent_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season: Mapped[str] = mapped_column(String(7), nullable=False)
    season_start_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    days_rest: Mapped[Decimal | None] = mapped_column(Numeric)
    is_back_to_back: Mapped[Decimal | None] = mapped_column(Numeric)

    roll5_pts: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_pts: Mapped[Decimal | None] = mapped_column(Numeric)
    roll15_pts: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_std_pts: Mapped[Decimal | None] = mapped_column(Numeric)
    roll5_reb: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_reb: Mapped[Decimal | None] = mapped_column(Numeric)
    roll15_reb: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_std_reb: Mapped[Decimal | None] = mapped_column(Numeric)
    roll5_ast: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_ast: Mapped[Decimal | None] = mapped_column(Numeric)
    roll15_ast: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_std_ast: Mapped[Decimal | None] = mapped_column(Numeric)
    roll5_fg3m: Mapped[Decimal | None] = mapped_column(Numeric)
    roll10_fg3m: Mapped[Decimal | None] = mapped_column(Numeric)
    roll15_fg3m: Mapped[Decimal | None] = mapped_column(Numeric)

    season_avg_pts: Mapped[Decimal | None] = mapped_column(Numeric)
    season_avg_reb: Mapped[Decimal | None] = mapped_column(Numeric)
    season_avg_ast: Mapped[Decimal | None] = mapped_column(Numeric)
    season_avg_fg3m: Mapped[Decimal | None] = mapped_column(Numeric)

    roll_minutes: Mapped[Decimal | None] = mapped_column(Numeric)
    usage_rate: Mapped[Decimal | None] = mapped_column(Numeric)
    minutes_trend: Mapped[Decimal | None] = mapped_column(Numeric)

    opp_def_rating: Mapped[Decimal | None] = mapped_column(Numeric)
    opp_pace: Mapped[Decimal | None] = mapped_column(Numeric)
    opp_pos_def: Mapped[Decimal | None] = mapped_column(Numeric)

    # From RAPM snapshots — NULL until T3.9.
    player_rapm: Mapped[Decimal | None] = mapped_column(Numeric)

    feature_version: Mapped[str] = mapped_column(String, nullable=False)


class FeatureGameState(CreatedAtMixin, Base):
    """Live game-state feature row — PK (game_id, event_num). Populated starting T4.1.

    feature-engineering.md §4 (game-state): score/clock, possession, the pre-game win-prob
    prior, and secondary context — drives the live win-probability model.
    """

    __tablename__ = "features_game_state"

    game_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("games.game_id"), primary_key=True, index=True
    )
    event_num: Mapped[int] = mapped_column(Integer, primary_key=True)

    score_diff: Mapped[int] = mapped_column(Integer, nullable=False)
    seconds_remaining_game: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    is_clutch: Mapped[bool] = mapped_column(Boolean, nullable=False)
    offense_has_ball: Mapped[bool] = mapped_column(Boolean, nullable=False)
    possession_arrow: Mapped[bool | None] = mapped_column(Boolean)
    pre_game_win_prob: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    timeouts_remaining_home: Mapped[int | None] = mapped_column(Integer)
    timeouts_remaining_away: Mapped[int | None] = mapped_column(Integer)
    in_bonus: Mapped[bool | None] = mapped_column(Boolean)
    home_fouls: Mapped[int | None] = mapped_column(Integer)
    away_fouls: Mapped[int | None] = mapped_column(Integer)
    home_win: Mapped[bool | None] = mapped_column(Boolean)  # training label, NULL live

    feature_version: Mapped[str] = mapped_column(String, nullable=False)
