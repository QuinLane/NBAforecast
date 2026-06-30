"""Assert silver Parquet schemas mirror the silver Postgres tables (data-model §3)."""

from nbaforecast.storage import models  # noqa: F401
from nbaforecast.storage.database import Base
from nbaforecast.storage.parquet_schemas import PARTITION_COLUMN, SILVER_PARQUET_SCHEMAS

_SILVER_TABLES = {
    "games",
    "team_game_stats",
    "player_game_stats",
    "play_by_play",
    "shots",
    "possessions",
}
# Serving-only columns omitted from the analytical store: operational timestamps and the
# BIGSERIAL surrogate PKs (Parquet keys rows by the natural key instead).
_SERVING_ONLY_COLUMNS = {"created_at", "updated_at", "shot_id", "possession_id"}


def test_every_silver_table_has_a_parquet_schema() -> None:
    assert set(SILVER_PARQUET_SCHEMAS) == _SILVER_TABLES


def test_parquet_columns_mirror_postgres_minus_timestamps_plus_partition() -> None:
    for table_name, schema in SILVER_PARQUET_SCHEMAS.items():
        pg_cols = {c.name for c in Base.metadata.tables[table_name].columns}
        expected = (pg_cols - _SERVING_ONLY_COLUMNS) | {PARTITION_COLUMN}
        assert set(schema.names) == expected, table_name


def test_partition_column_present_and_non_nullable() -> None:
    for table_name, schema in SILVER_PARQUET_SCHEMAS.items():
        field = schema.field(PARTITION_COLUMN)
        assert not field.nullable, table_name
