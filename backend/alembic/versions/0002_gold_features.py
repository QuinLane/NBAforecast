"""gold feature tables

Creates data-model.md §4 — features_team_game, features_player_game, features_game_state.
features_team_game is populated starting now (T2.3); the other two are scaffolded ahead of
their builders (T3.2, T4.1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "features_team_game",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_team_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.String(length=7), nullable=False),
        sa.Column("season_start_year", sa.Integer(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("days_rest", sa.Numeric(), nullable=True),
        sa.Column("is_back_to_back", sa.Numeric(), nullable=True),
        sa.Column("games_last_7d", sa.Integer(), nullable=True),
        sa.Column("games_last_14d", sa.Integer(), nullable=True),
        sa.Column("travel_distance_km", sa.Numeric(), nullable=True),
        sa.Column("tz_shift", sa.Numeric(), nullable=True),
        sa.Column("roll5_net_rating", sa.Numeric(), nullable=True),
        sa.Column("roll10_net_rating", sa.Numeric(), nullable=True),
        sa.Column("roll5_off_rating", sa.Numeric(), nullable=True),
        sa.Column("roll10_off_rating", sa.Numeric(), nullable=True),
        sa.Column("roll5_def_rating", sa.Numeric(), nullable=True),
        sa.Column("roll10_def_rating", sa.Numeric(), nullable=True),
        sa.Column("roll5_pace", sa.Numeric(), nullable=True),
        sa.Column("roll10_pace", sa.Numeric(), nullable=True),
        sa.Column("season_off_rating", sa.Numeric(), nullable=True),
        sa.Column("season_def_rating", sa.Numeric(), nullable=True),
        sa.Column("season_net_rating", sa.Numeric(), nullable=True),
        sa.Column("season_pace", sa.Numeric(), nullable=True),
        sa.Column("win_pct_to_date", sa.Numeric(), nullable=True),
        sa.Column("elo", sa.Numeric(), nullable=False),
        sa.Column("opp_adj_net_rating", sa.Numeric(), nullable=True),
        sa.Column("h2h_record", sa.Numeric(), nullable=True),
        sa.Column("h2h_avg_margin", sa.Numeric(), nullable=True),
        sa.Column("rest_advantage", sa.Numeric(), nullable=True),
        sa.Column("rating_diff", sa.Numeric(), nullable=True),
        sa.Column("elo_diff", sa.Numeric(), nullable=True),
        sa.Column("team_orapm", sa.Numeric(), nullable=True),
        sa.Column("team_drapm", sa.Numeric(), nullable=True),
        sa.Column("feature_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_features_team_game_game_id_games"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.team_id"], name="fk_features_team_game_team_id_teams"
        ),
        sa.PrimaryKeyConstraint("game_id", "team_id", name="pk_features_team_game"),
    )
    op.create_index("ix_features_team_game_game_id", "features_team_game", ["game_id"])
    op.create_index("ix_features_team_game_team_id", "features_team_game", ["team_id"])
    op.create_index(
        "ix_features_team_game_season_start_year", "features_team_game", ["season_start_year"]
    )

    op.create_table(
        "features_player_game",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_team_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.String(length=7), nullable=False),
        sa.Column("season_start_year", sa.Integer(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("days_rest", sa.Numeric(), nullable=True),
        sa.Column("is_back_to_back", sa.Numeric(), nullable=True),
        sa.Column("roll5_pts", sa.Numeric(), nullable=True),
        sa.Column("roll10_pts", sa.Numeric(), nullable=True),
        sa.Column("roll15_pts", sa.Numeric(), nullable=True),
        sa.Column("roll10_std_pts", sa.Numeric(), nullable=True),
        sa.Column("roll5_reb", sa.Numeric(), nullable=True),
        sa.Column("roll10_reb", sa.Numeric(), nullable=True),
        sa.Column("roll15_reb", sa.Numeric(), nullable=True),
        sa.Column("roll10_std_reb", sa.Numeric(), nullable=True),
        sa.Column("roll5_ast", sa.Numeric(), nullable=True),
        sa.Column("roll10_ast", sa.Numeric(), nullable=True),
        sa.Column("roll15_ast", sa.Numeric(), nullable=True),
        sa.Column("roll10_std_ast", sa.Numeric(), nullable=True),
        sa.Column("roll5_fg3m", sa.Numeric(), nullable=True),
        sa.Column("roll10_fg3m", sa.Numeric(), nullable=True),
        sa.Column("roll15_fg3m", sa.Numeric(), nullable=True),
        sa.Column("season_avg_pts", sa.Numeric(), nullable=True),
        sa.Column("season_avg_reb", sa.Numeric(), nullable=True),
        sa.Column("season_avg_ast", sa.Numeric(), nullable=True),
        sa.Column("season_avg_fg3m", sa.Numeric(), nullable=True),
        sa.Column("roll_minutes", sa.Numeric(), nullable=True),
        sa.Column("usage_rate", sa.Numeric(), nullable=True),
        sa.Column("minutes_trend", sa.Numeric(), nullable=True),
        sa.Column("opp_def_rating", sa.Numeric(), nullable=True),
        sa.Column("opp_pace", sa.Numeric(), nullable=True),
        sa.Column("opp_pos_def", sa.Numeric(), nullable=True),
        sa.Column("player_rapm", sa.Numeric(), nullable=True),
        sa.Column("feature_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_features_player_game_game_id_games"
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.player_id"], name="fk_features_player_game_player_id_players"
        ),
        sa.PrimaryKeyConstraint("game_id", "player_id", name="pk_features_player_game"),
    )
    op.create_index("ix_features_player_game_game_id", "features_player_game", ["game_id"])
    op.create_index("ix_features_player_game_player_id", "features_player_game", ["player_id"])
    op.create_index(
        "ix_features_player_game_season_start_year", "features_player_game", ["season_start_year"]
    )

    op.create_table(
        "features_game_state",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("event_num", sa.Integer(), nullable=False),
        sa.Column("score_diff", sa.Integer(), nullable=False),
        sa.Column("seconds_remaining_game", sa.Integer(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("is_clutch", sa.Boolean(), nullable=False),
        sa.Column("offense_has_ball", sa.Boolean(), nullable=False),
        sa.Column("possession_arrow", sa.Boolean(), nullable=True),
        sa.Column("pre_game_win_prob", sa.Numeric(), nullable=False),
        sa.Column("timeouts_remaining_home", sa.Integer(), nullable=True),
        sa.Column("timeouts_remaining_away", sa.Integer(), nullable=True),
        sa.Column("in_bonus", sa.Boolean(), nullable=True),
        sa.Column("home_fouls", sa.Integer(), nullable=True),
        sa.Column("away_fouls", sa.Integer(), nullable=True),
        sa.Column("home_win", sa.Boolean(), nullable=True),
        sa.Column("feature_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_features_game_state_game_id_games"
        ),
        sa.PrimaryKeyConstraint("game_id", "event_num", name="pk_features_game_state"),
    )
    op.create_index("ix_features_game_state_game_id", "features_game_state", ["game_id"])


def downgrade() -> None:
    op.drop_table("features_game_state")
    op.drop_table("features_player_game")
    op.drop_table("features_team_game")
