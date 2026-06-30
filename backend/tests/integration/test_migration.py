"""Alembic round-trip against a real Postgres (skipped when no DB is reachable).

Runs ``alembic upgrade head`` → asserts every data-model §§2,3,4,5 table exists with its primary
key → ``downgrade base`` removes them → re-upgrades so the DB is left at head for other tests.
This is the live proof of the T1.1/T2.3 definition of done; offline structural checks live in
``tests/unit/test_schema.py``.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from nbaforecast.config.settings import get_settings

psycopg = pytest.importorskip("psycopg")

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Tables created by migration 0001 → expected primary-key columns.
EXPECTED_TABLES = {
    "teams": ["team_id"],
    "players": ["player_id"],
    "games": ["game_id"],
    "team_game_stats": ["game_id", "team_id"],
    "player_game_stats": ["game_id", "player_id"],
    "play_by_play": ["game_id", "event_num"],
    "shots": ["shot_id"],
    "possessions": ["possession_id"],
    "player_rapm": ["player_id", "as_of_date", "window"],
    "predictions": ["prediction_id"],
    "live_win_prob_timeline": ["game_id", "event_num"],
    "ingested_games": ["game_id"],
    "features_team_game": ["game_id", "team_id"],
    "features_player_game": ["game_id", "player_id"],
    "features_game_state": ["game_id", "event_num"],
}


def _sync_dsn() -> str:
    """Postgres URL with a sync (psycopg) driver for assertions."""
    return get_settings().postgres_url.replace("+asyncpg", "")


def _db_reachable() -> bool:
    try:
        with psycopg.connect(_sync_dsn(), connect_timeout=3):
            return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_reachable(), reason="Postgres not reachable; skipping live migration test"
)


def _alembic(*args: str) -> None:
    subprocess.run(  # noqa: S603 — fixed argv (no shell), trusted alembic invocation
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )


def _table_pks() -> dict[str, list[str]]:
    """Map of public table name → ordered primary-key column names."""
    query = """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
        ORDER BY tc.table_name, kcu.ordinal_position
    """
    pks: dict[str, list[str]] = {}
    with psycopg.connect(_sync_dsn()) as conn, conn.cursor() as cur:
        cur.execute(query)
        for table, column in cur.fetchall():
            pks.setdefault(table, []).append(column)
    return pks


def test_migration_round_trip() -> None:
    _alembic("downgrade", "base")  # clean slate regardless of prior state
    try:
        _alembic("upgrade", "head")
        pks = _table_pks()
        for table, expected_pk in EXPECTED_TABLES.items():
            assert table in pks, f"{table} missing after upgrade"
            assert pks[table] == expected_pk, f"{table} PK mismatch: {pks[table]}"

        _alembic("downgrade", "base")
        remaining = set(_table_pks()) & set(EXPECTED_TABLES)
        assert not remaining, f"tables survived downgrade: {remaining}"
    finally:
        _alembic("upgrade", "head")  # leave DB usable for other tests
