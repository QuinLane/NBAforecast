"""PyArrow schemas mirroring the silver tables for the partitioned analytical store.

Each silver table (data-model §3) is also written to Parquet under
``silver/{table}/season_start_year={YYYY}/part-*.parquet`` for fast columnar training reads
([data-pipeline.md §4](../../../plans/data-pipeline.md)). These schemas are the contract for
:func:`nbaforecast.storage.write_parquet` (T1.4).

Conventions vs. the Postgres schema:
- ``NUMERIC`` columns become ``float64`` — the analytical store is float-native and training reads
  floats; the exact-decimal Postgres copy remains the serving source of truth.
- Operational timestamps (``created_at`` / ``updated_at``) are omitted; they are serving metadata.
- ``season_start_year`` is included on every table as the partition column, even where the silver
  Postgres table derives it via the ``games`` join.

Gold ``features_*`` Parquet schemas (data-model §4) are added with T2.3.
"""

import pyarrow as pa

# Partition column present on every silver Parquet dataset.
_SEASON_PARTITION = pa.field("season_start_year", pa.int32(), nullable=False)

GAMES_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("season", pa.string(), nullable=False),
        _SEASON_PARTITION,
        pa.field("season_type", pa.string(), nullable=False),
        pa.field("game_date", pa.date32(), nullable=False),
        pa.field("game_datetime", pa.timestamp("us", tz="UTC")),
        pa.field("home_team_id", pa.int64(), nullable=False),
        pa.field("away_team_id", pa.int64(), nullable=False),
        pa.field("home_score", pa.int32()),
        pa.field("away_score", pa.int32()),
        pa.field("status", pa.string(), nullable=False),
        pa.field("num_periods", pa.int32(), nullable=False),
    ]
)

TEAM_GAME_STATS_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("team_id", pa.int64(), nullable=False),
        _SEASON_PARTITION,
        pa.field("opponent_team_id", pa.int64(), nullable=False),
        pa.field("is_home", pa.bool_(), nullable=False),
        *[
            pa.field(c, pa.int32(), nullable=False)
            for c in (
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
        ],
        *[
            pa.field(c, pa.float64())
            for c in (
                "off_rating",
                "def_rating",
                "net_rating",
                "pace",
                "possessions",
            )
        ],
    ]
)

PLAYER_GAME_STATS_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("player_id", pa.int64(), nullable=False),
        _SEASON_PARTITION,
        pa.field("team_id", pa.int64(), nullable=False),
        pa.field("opponent_team_id", pa.int64(), nullable=False),
        pa.field("is_home", pa.bool_(), nullable=False),
        pa.field("started", pa.bool_(), nullable=False),
        pa.field("min", pa.float64()),
        *[
            pa.field(c, pa.int32(), nullable=False)
            for c in (
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
        ],
        pa.field("plus_minus", pa.int32()),
        pa.field("usage_rate", pa.float64()),
    ]
)

PLAY_BY_PLAY_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("event_num", pa.int32(), nullable=False),
        _SEASON_PARTITION,
        pa.field("period", pa.int32(), nullable=False),
        pa.field("pc_time", pa.string()),
        pa.field("seconds_remaining_period", pa.int32()),
        pa.field("event_msg_type", pa.int32()),
        pa.field("event_action_type", pa.int32()),
        pa.field("description", pa.string()),
        pa.field("home_score", pa.int32()),
        pa.field("away_score", pa.int32()),
        pa.field("player1_id", pa.int64()),
        pa.field("player2_id", pa.int64()),
        pa.field("player3_id", pa.int64()),
        pa.field("team_id", pa.int64()),
    ]
)

SHOTS_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("event_num", pa.int32(), nullable=False),
        _SEASON_PARTITION,
        pa.field("player_id", pa.int64(), nullable=False),
        pa.field("team_id", pa.int64(), nullable=False),
        pa.field("period", pa.int32(), nullable=False),
        pa.field("seconds_remaining_period", pa.int32()),
        pa.field("loc_x", pa.int32()),
        pa.field("loc_y", pa.int32()),
        pa.field("shot_distance", pa.int32()),
        pa.field("shot_zone", pa.string()),
        pa.field("shot_zone_area", pa.string()),
        pa.field("shot_zone_range", pa.string()),
        pa.field("shot_type", pa.string()),
        pa.field("action_type", pa.string()),
        pa.field("made", pa.bool_(), nullable=False),
        pa.field("location_reliable", pa.bool_(), nullable=False),
    ]
)

POSSESSIONS_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        _SEASON_PARTITION,
        pa.field("period", pa.int32(), nullable=False),
        pa.field("start_seconds", pa.int32()),
        pa.field("end_seconds", pa.int32()),
        pa.field("offense_team_id", pa.int64(), nullable=False),
        pa.field("defense_team_id", pa.int64(), nullable=False),
        pa.field("points", pa.int32(), nullable=False),
        pa.field("off_player_ids", pa.list_(pa.int64()), nullable=False),
        pa.field("def_player_ids", pa.list_(pa.int64()), nullable=False),
    ]
)

# Table name → schema. Partition column is ``season_start_year`` for all.
SILVER_PARQUET_SCHEMAS: dict[str, pa.Schema] = {
    "games": GAMES_SCHEMA,
    "team_game_stats": TEAM_GAME_STATS_SCHEMA,
    "player_game_stats": PLAYER_GAME_STATS_SCHEMA,
    "play_by_play": PLAY_BY_PLAY_SCHEMA,
    "shots": SHOTS_SCHEMA,
    "possessions": POSSESSIONS_SCHEMA,
}

PARTITION_COLUMN = "season_start_year"
