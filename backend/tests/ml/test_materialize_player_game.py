"""Unit tests for player-game feature materialization (feature-engineering.md Prompt 5),
mirroring ``test_materialize.py`` for team-game.
"""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from nbaforecast.features.materialize import (
    PLAYER_GAME_FEATURE_VERSION,
    materialize_player_game_features,
    write_player_game_features_parquet,
)

TEAM_A, TEAM_B = 1, 2
PLAYER_A, PLAYER_B = 101, 201


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
                "def_rating": 100,
                "pace": 98,
            },
            {
                "game_id": "G1",
                "team_id": TEAM_B,
                "opponent_team_id": TEAM_A,
                "is_home": False,
                "def_rating": 115,
                "pace": 98,
            },
            {
                "game_id": "G2",
                "team_id": TEAM_B,
                "opponent_team_id": TEAM_A,
                "is_home": True,
                "def_rating": 105,
                "pace": 96,
            },
            {
                "game_id": "G2",
                "team_id": TEAM_A,
                "opponent_team_id": TEAM_B,
                "is_home": False,
                "def_rating": 95,
                "pace": 96,
            },
        ]
    )


def _player_game_stats() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "G1",
                "player_id": PLAYER_A,
                "team_id": TEAM_A,
                "opponent_team_id": TEAM_B,
                "is_home": True,
                "min": 30,
                "pts": 20,
                "reb": 5,
                "ast": 4,
                "fg3m": 2,
                "usage_rate": 0.25,
            },
            {
                "game_id": "G1",
                "player_id": PLAYER_B,
                "team_id": TEAM_B,
                "opponent_team_id": TEAM_A,
                "is_home": False,
                "min": 28,
                "pts": 12,
                "reb": 8,
                "ast": 2,
                "fg3m": 1,
                "usage_rate": 0.18,
            },
            {
                "game_id": "G2",
                "player_id": PLAYER_A,
                "team_id": TEAM_A,
                "opponent_team_id": TEAM_B,
                "is_home": False,
                "min": 32,
                "pts": 24,
                "reb": 6,
                "ast": 5,
                "fg3m": 3,
                "usage_rate": 0.27,
            },
            {
                "game_id": "G2",
                "player_id": PLAYER_B,
                "team_id": TEAM_B,
                "opponent_team_id": TEAM_A,
                "is_home": True,
                "min": 26,
                "pts": 10,
                "reb": 7,
                "ast": 3,
                "fg3m": 0,
                "usage_rate": 0.17,
            },
        ]
    )


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": PLAYER_A, "position": "G"},
            {"player_id": PLAYER_B, "position": "F"},
        ]
    )


def test_materialize_stamps_feature_version() -> None:
    out = materialize_player_game_features(
        _games(), _player_game_stats(), _team_game_stats(), _players()
    )
    assert (out["feature_version"] == PLAYER_GAME_FEATURE_VERSION).all()


def test_materialize_player_rapm_is_null_placeholder() -> None:
    out = materialize_player_game_features(
        _games(), _player_game_stats(), _team_game_stats(), _players()
    )
    assert out["player_rapm"].isna().all()


def test_materialize_without_game_ids_includes_full_history() -> None:
    out = materialize_player_game_features(
        _games(), _player_game_stats(), _team_game_stats(), _players()
    )
    assert set(out["game_id"]) == {"G1", "G2"}
    assert len(out) == 4  # 2 games x 2 players


def test_materialize_with_game_ids_narrows_output_only() -> None:
    out = materialize_player_game_features(
        _games(), _player_game_stats(), _team_game_stats(), _players(), game_ids=["G2"]
    )
    assert set(out["game_id"]) == {"G2"}
    assert len(out) == 2  # 1 game x 2 players

    # The narrowed row still reflects full-history computation context (not recomputed in
    # isolation) — player A's rolling pts entering G2 sees G1's result.
    player_a_row = out.loc[out["player_id"] == PLAYER_A].iloc[0]
    assert player_a_row["roll5_pts"] == 20.0


def test_write_player_game_features_parquet_one_file_per_game(tmp_path: Path) -> None:
    features = materialize_player_game_features(
        _games(), _player_game_stats(), _team_game_stats(), _players()
    )
    paths = write_player_game_features_parquet(features, root=str(tmp_path))

    assert len(paths) == 2  # one part-file per game_id
    for path in paths:
        assert path.exists()
    g1_path = next(p for p in paths if "G1" in p.name)
    table = pq.read_table(g1_path)
    assert table.num_rows == 2  # both players' rows for that game
    assert set(table.column("feature_version").to_pylist()) == {PLAYER_GAME_FEATURE_VERSION}


def test_write_player_game_features_parquet_is_idempotent_for_same_game(tmp_path: Path) -> None:
    features = materialize_player_game_features(
        _games(), _player_game_stats(), _team_game_stats(), _players()
    )
    write_player_game_features_parquet(features, root=str(tmp_path))
    write_player_game_features_parquet(features, root=str(tmp_path))

    part_dir = tmp_path / "features_player_game" / "season_start_year=2023"
    g1_files = list(part_dir.glob("part-G1.parquet"))
    assert len(g1_files) == 1
