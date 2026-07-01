"""Unit tests for the sparse RAPM design matrix (rapm.md Prompt 2)."""

import pandas as pd
import pytest
from nbaforecast.models.rapm.design import build_design_matrix
from nbaforecast.models.rapm.stints import build_stints, stints_to_dataframe
from scipy import sparse


def _stints_df() -> pd.DataFrame:
    possessions = pd.DataFrame(
        [
            {
                "game_id": "G1",
                "period": 1,
                "start_seconds": 0,
                "offense_team_id": 100,
                "defense_team_id": 200,
                "points": 2,
                "off_player_ids": [1, 2, 3, 4, 5],
                "def_player_ids": [11, 12, 13, 14, 15],
            },
            {
                "game_id": "G1",
                "period": 1,
                "start_seconds": 20,
                "offense_team_id": 100,
                "defense_team_id": 200,
                "points": 0,
                "off_player_ids": [1, 2, 3, 4, 5],
                "def_player_ids": [11, 12, 13, 14, 15],
            },
            {
                "game_id": "G1",
                "period": 1,
                "start_seconds": 40,
                "offense_team_id": 200,
                "defense_team_id": 100,
                "points": 3,
                "off_player_ids": [11, 12, 13, 14, 16],
                "def_player_ids": [1, 2, 3, 4, 5],
            },
        ]
    )
    return stints_to_dataframe(build_stints(possessions))


def test_build_design_matrix_shape() -> None:
    design = build_design_matrix(_stints_df())
    # 2 stints (first two possessions merge; third has a different lineup).
    assert design.x.shape[0] == 2
    # Players appearing across either lineup: {1,2,3,4,5} + {11,12,13,14,15,16} = 11.
    n_players = len({1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 16})
    assert design.x.shape[1] == 2 * n_players
    assert design.player_index.n_columns == 2 * n_players


def test_build_design_matrix_offense_defense_columns_set_correctly() -> None:
    design = build_design_matrix(_stints_df())
    row0 = design.x[0].toarray().ravel()
    for player_id in (1, 2, 3, 4, 5):
        assert row0[design.player_index.offense_column(player_id)] == 1.0
    for player_id in (11, 12, 13, 14, 15):
        assert row0[design.player_index.defense_column(player_id)] == 1.0
    assert row0.sum() == 10.0  # no other columns set for this row


def test_build_design_matrix_target_is_points_per_100_possessions() -> None:
    design = build_design_matrix(_stints_df())
    # First stint: 2 possessions, 2 points total -> 100 pts/100 poss.
    assert design.y[0] == pytest.approx(100.0)
    # Second stint: 1 possession, 3 points -> 300 pts/100 poss.
    assert design.y[1] == pytest.approx(300.0)


def test_build_design_matrix_weights_are_possession_counts() -> None:
    design = build_design_matrix(_stints_df())
    assert design.weights[0] == 2
    assert design.weights[1] == 1


def test_build_design_matrix_empty_input() -> None:
    design = build_design_matrix(pd.DataFrame())
    assert design.x.shape == (0, 0)
    assert design.y.size == 0
    assert design.player_index.n_columns == 0


def test_game_ids_aligned_with_rows() -> None:
    design = build_design_matrix(_stints_df())
    assert list(design.game_ids) == ["G1", "G1"]


def test_design_matrix_is_sparse_csr() -> None:
    design = build_design_matrix(_stints_df())
    assert isinstance(design.x, sparse.csr_matrix)
