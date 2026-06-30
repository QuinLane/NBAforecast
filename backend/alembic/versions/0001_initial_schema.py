"""initial schema (reference, silver, serving tables)

Creates data-model.md §§2, 3, 5 — reference/dimension, core silver, and model/serving tables.
Gold ``features_*`` tables (§4) are added later by T2.3.

Revision ID: 0001
Revises:
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("team_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("abbreviation", sa.String(length=5), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("nickname", sa.String(), nullable=True),
        sa.Column("conference", sa.String(), nullable=True),
        sa.Column("division", sa.String(), nullable=True),
        sa.Column("arena_name", sa.String(), nullable=True),
        sa.Column("arena_lat", sa.Numeric(), nullable=True),
        sa.Column("arena_lon", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("team_id", name="pk_teams"),
    )

    op.create_table(
        "players",
        sa.Column("player_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("position", sa.String(), nullable=True),
        sa.Column("height_inches", sa.Integer(), nullable=True),
        sa.Column("weight_lbs", sa.Integer(), nullable=True),
        sa.Column("birthdate", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("player_id", name="pk_players"),
    )

    op.create_table(
        "games",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("season", sa.String(length=7), nullable=False),
        sa.Column("season_start_year", sa.Integer(), nullable=False),
        sa.Column("season_type", sa.String(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("game_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team_id", sa.BigInteger(), nullable=False),
        sa.Column("away_team_id", sa.BigInteger(), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("num_periods", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint("home_team_id <> away_team_id", name="ck_games_home_away_distinct"),
        sa.ForeignKeyConstraint(
            ["home_team_id"], ["teams.team_id"], name="fk_games_home_team_id_teams"
        ),
        sa.ForeignKeyConstraint(
            ["away_team_id"], ["teams.team_id"], name="fk_games_away_team_id_teams"
        ),
        sa.PrimaryKeyConstraint("game_id", name="pk_games"),
    )
    op.create_index("ix_games_season_start_year", "games", ["season_start_year"])
    op.create_index("ix_games_game_date", "games", ["game_date"])
    op.create_index("ix_games_home_team_id", "games", ["home_team_id"])
    op.create_index("ix_games_away_team_id", "games", ["away_team_id"])

    _counting = (
        "pts",
        "reb",
        "oreb",
        "dreb",
        "ast",
        "stl",
        "blk",
        "tov",
        "pf",
        "fgm",
        "fga",
        "fg3m",
        "fg3a",
        "ftm",
        "fta",
    )

    op.create_table(
        "team_game_stats",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_team_id", sa.BigInteger(), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        *[sa.Column(c, sa.Integer(), nullable=False) for c in _counting],
        sa.Column("off_rating", sa.Numeric(), nullable=True),
        sa.Column("def_rating", sa.Numeric(), nullable=True),
        sa.Column("net_rating", sa.Numeric(), nullable=True),
        sa.Column("pace", sa.Numeric(), nullable=True),
        sa.Column("possessions", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_team_game_stats_game_id_games"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.team_id"], name="fk_team_game_stats_team_id_teams"
        ),
        sa.PrimaryKeyConstraint("game_id", "team_id", name="pk_team_game_stats"),
    )
    op.create_index("ix_team_game_stats_team_id", "team_game_stats", ["team_id"])

    op.create_table(
        "player_game_stats",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent_team_id", sa.BigInteger(), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("started", sa.Boolean(), nullable=False),
        sa.Column("min", sa.Numeric(), nullable=True),
        *[sa.Column(c, sa.Integer(), nullable=False) for c in _counting],
        sa.Column("plus_minus", sa.Integer(), nullable=True),
        sa.Column("usage_rate", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_player_game_stats_game_id_games"
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.player_id"], name="fk_player_game_stats_player_id_players"
        ),
        sa.PrimaryKeyConstraint("game_id", "player_id", name="pk_player_game_stats"),
    )
    op.create_index("ix_player_game_stats_player_id", "player_game_stats", ["player_id"])
    op.create_index("ix_player_game_stats_team_id", "player_game_stats", ["team_id"])

    op.create_table(
        "play_by_play",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("event_num", sa.Integer(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("pc_time", sa.String(), nullable=True),
        sa.Column("seconds_remaining_period", sa.Integer(), nullable=True),
        sa.Column("event_msg_type", sa.Integer(), nullable=True),
        sa.Column("event_action_type", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("player1_id", sa.BigInteger(), nullable=True),
        sa.Column("player2_id", sa.BigInteger(), nullable=True),
        sa.Column("player3_id", sa.BigInteger(), nullable=True),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_play_by_play_game_id_games"
        ),
        sa.PrimaryKeyConstraint("game_id", "event_num", name="pk_play_by_play"),
    )
    op.create_index("ix_play_by_play_game_id_period", "play_by_play", ["game_id", "period"])

    op.create_table(
        "shots",
        sa.Column("shot_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("event_num", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("seconds_remaining_period", sa.Integer(), nullable=True),
        sa.Column("loc_x", sa.Integer(), nullable=True),
        sa.Column("loc_y", sa.Integer(), nullable=True),
        sa.Column("shot_distance", sa.Integer(), nullable=True),
        sa.Column("shot_zone", sa.String(), nullable=True),
        sa.Column("shot_zone_area", sa.String(), nullable=True),
        sa.Column("shot_zone_range", sa.String(), nullable=True),
        sa.Column("shot_type", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=True),
        sa.Column("made", sa.Boolean(), nullable=False),
        sa.Column("location_reliable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.game_id"], name="fk_shots_game_id_games"),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.player_id"], name="fk_shots_player_id_players"
        ),
        sa.PrimaryKeyConstraint("shot_id", name="pk_shots"),
        sa.UniqueConstraint("game_id", "event_num", name="uq_shots_game_id_event_num"),
    )
    op.create_index("ix_shots_game_id", "shots", ["game_id"])
    op.create_index("ix_shots_player_id", "shots", ["player_id"])
    op.create_index("ix_shots_shot_zone", "shots", ["shot_zone"])

    op.create_table(
        "possessions",
        sa.Column("possession_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Integer(), nullable=True),
        sa.Column("end_seconds", sa.Integer(), nullable=True),
        sa.Column("offense_team_id", sa.BigInteger(), nullable=False),
        sa.Column("defense_team_id", sa.BigInteger(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("off_player_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("def_player_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_possessions_game_id_games"
        ),
        sa.PrimaryKeyConstraint("possession_id", name="pk_possessions"),
    )
    op.create_index("ix_possessions_game_id", "possessions", ["game_id"])

    op.create_table(
        "player_rapm",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("window", sa.Integer(), nullable=False),
        sa.Column("orapm", sa.Numeric(), nullable=True),
        sa.Column("drapm", sa.Numeric(), nullable=True),
        sa.Column("rapm", sa.Numeric(), nullable=True),
        sa.Column("possessions", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.player_id"], name="fk_player_rapm_player_id_players"
        ),
        sa.PrimaryKeyConstraint("player_id", "as_of_date", "window", name="pk_player_rapm"),
    )
    op.create_index("ix_player_rapm_player_id", "player_rapm", ["player_id"])
    op.create_index("ix_player_rapm_as_of_date", "player_rapm", ["as_of_date"])

    op.create_table(
        "predictions",
        sa.Column("prediction_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=True),
        sa.Column("head", sa.String(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("interval_low", sa.Numeric(), nullable=True),
        sa.Column("interval_high", sa.Numeric(), nullable=True),
        sa.Column("market", sa.Numeric(), nullable=True),
        sa.Column("mlflow_run_id", sa.String(), nullable=False),
        sa.Column("feature_version", sa.String(), nullable=False),
        sa.Column("explanation", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_predictions_game_id_games"
        ),
        sa.PrimaryKeyConstraint("prediction_id", name="pk_predictions"),
    )
    op.create_index("ix_predictions_game_id", "predictions", ["game_id"])

    op.create_table(
        "live_win_prob_timeline",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("event_num", sa.Integer(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("seconds_remaining_game", sa.Integer(), nullable=False),
        sa.Column("score_diff", sa.Integer(), nullable=False),
        sa.Column("win_prob", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.game_id"], name="fk_live_win_prob_timeline_game_id_games"
        ),
        sa.PrimaryKeyConstraint("game_id", "event_num", name="pk_live_win_prob_timeline"),
    )
    op.create_index("ix_live_win_prob_timeline_game_id", "live_win_prob_timeline", ["game_id"])

    op.create_table(
        "ingested_games",
        sa.Column("game_id", sa.String(length=20), nullable=False),
        sa.Column("entities_done", postgresql.JSONB(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("game_id", name="pk_ingested_games"),
    )


def downgrade() -> None:
    op.drop_table("ingested_games")
    op.drop_table("live_win_prob_timeline")
    op.drop_table("predictions")
    op.drop_table("player_rapm")
    op.drop_table("possessions")
    op.drop_table("shots")
    op.drop_table("play_by_play")
    op.drop_table("player_game_stats")
    op.drop_table("team_game_stats")
    op.drop_table("games")
    op.drop_table("players")
    op.drop_table("teams")
