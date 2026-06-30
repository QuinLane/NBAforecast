"""Unit tests for feature materialization (feature-engineering.md Prompt 5).

Covers the pure parts: feature_version stamping, the incremental game_ids filter, and the
Parquet partition layout. Postgres upsert is exercised indirectly via the schema-match test
(``test_schema.py``) and the live migration test; round-tripping a real upsert needs a DB and is
out of scope for unit tests here.
"""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from nbaforecast.features.materialize import (
    TEAM_GAME_FEATURE_VERSION,
    materialize_team_game_features,
    write_team_game_features_parquet,
)

TEAM_A, TEAM_B = 1, 2


def _games() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "G1",
                "season": "2023-24",
                "season_start_year": 2023,
                "game_date": "2023-10-24",
                "home_team_id": TEAM_A,
                "away_team_id": TEAM_B,
                "home_score": 110,
                "away_score": 100,
                "status": "final",
            },
            {
                "game_id": "G2",
                "season": "2023-24",
                "season_start_year": 2023,
                "game_date": "2023-10-26",
                "home_team_id": TEAM_B,
                "away_team_id": TEAM_A,
                "home_score": 95,
                "away_score": 105,
                "status": "final",
            },
        ]
    )


def _team_game_stats() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "G1",
                "team_id": TEAM_A,
                "opponent_team_id": TEAM_B,
                "is_home": True,
                "off_rating": 115,
                "def_rating": 100,
                "net_rating": 15,
                "pace": 98,
            },
            {
                "game_id": "G1",
                "team_id": TEAM_B,
                "opponent_team_id": TEAM_A,
                "is_home": False,
                "off_rating": 100,
                "def_rating": 115,
                "net_rating": -15,
                "pace": 98,
            },
            {
                "game_id": "G2",
                "team_id": TEAM_B,
                "opponent_team_id": TEAM_A,
                "is_home": True,
                "off_rating": 95,
                "def_rating": 105,
                "net_rating": -10,
                "pace": 96,
            },
            {
                "game_id": "G2",
                "team_id": TEAM_A,
                "opponent_team_id": TEAM_B,
                "is_home": False,
                "off_rating": 105,
                "def_rating": 95,
                "net_rating": 10,
                "pace": 96,
            },
        ]
    )


def _teams() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"team_id": TEAM_A, "arena_lat": 34.05, "arena_lon": -118.24},
            {"team_id": TEAM_B, "arena_lat": 40.71, "arena_lon": -74.01},
        ]
    )


def test_materialize_stamps_feature_version() -> None:
    out = materialize_team_game_features(_games(), _team_game_stats(), _teams())
    assert (out["feature_version"] == TEAM_GAME_FEATURE_VERSION).all()


def test_materialize_without_game_ids_includes_full_history() -> None:
    out = materialize_team_game_features(_games(), _team_game_stats(), _teams())
    assert set(out["game_id"]) == {"G1", "G2"}
    assert len(out) == 4  # 2 games x 2 teams


def test_materialize_with_game_ids_narrows_output_only() -> None:
    out = materialize_team_game_features(_games(), _team_game_stats(), _teams(), game_ids=["G2"])
    assert set(out["game_id"]) == {"G2"}
    assert len(out) == 2  # 1 game x 2 teams

    # The narrowed row still reflects full-history computation context (not recomputed in
    # isolation) — team A's rolling net rating entering G2 sees G1's result.
    team_a_row = out.loc[out["team_id"] == TEAM_A].iloc[0]
    assert team_a_row["roll5_net_rating"] == 15.0


def test_write_team_game_features_parquet_one_file_per_game(tmp_path: Path) -> None:
    features = materialize_team_game_features(_games(), _team_game_stats(), _teams())
    paths = write_team_game_features_parquet(features, root=str(tmp_path))

    assert len(paths) == 2  # one part-file per game_id
    for path in paths:
        assert path.exists()
    g1_path = next(p for p in paths if "G1" in p.name)
    table = pq.read_table(g1_path)
    assert table.num_rows == 2  # both teams' rows for that game
    assert set(table.column("feature_version").to_pylist()) == {TEAM_GAME_FEATURE_VERSION}


def test_write_team_game_features_parquet_is_idempotent_for_same_game(tmp_path: Path) -> None:
    features = materialize_team_game_features(_games(), _team_game_stats(), _teams())
    write_team_game_features_parquet(features, root=str(tmp_path))
    write_team_game_features_parquet(features, root=str(tmp_path))

    part_dir = tmp_path / "features_team_game" / "season_start_year=2023"
    g1_files = list(part_dir.glob("part-G1.parquet"))
    assert len(g1_files) == 1
