"""Unit tests for stint aggregation (rapm.md Prompt 1)."""

import pandas as pd
from nbaforecast.models.rapm.stints import build_stints, stints_to_dataframe

LINEUP_A_OFF = [1, 2, 3, 4, 5]
LINEUP_A_DEF = [11, 12, 13, 14, 15]
LINEUP_B_OFF = [1, 2, 3, 4, 6]  # one substitution vs. lineup A
LINEUP_B_DEF = [11, 12, 13, 14, 15]


def _possession(
    game_id: str,
    period: int,
    start_seconds: int,
    off_team: int,
    def_team: int,
    off_players: list[int],
    def_players: list[int],
    points: int,
) -> dict[str, object]:
    return {
        "game_id": game_id,
        "period": period,
        "start_seconds": start_seconds,
        "end_seconds": start_seconds + 20,
        "offense_team_id": off_team,
        "defense_team_id": def_team,
        "points": points,
        "off_player_ids": off_players,
        "def_player_ids": def_players,
    }


def test_build_stints_merges_consecutive_same_lineup_possessions() -> None:
    possessions = pd.DataFrame(
        [
            _possession("G1", 1, 0, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
            _possession("G1", 1, 20, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 0),
            _possession("G1", 1, 40, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 3),
        ]
    )
    stints = build_stints(possessions)
    assert len(stints) == 1
    assert stints[0].points == 5
    assert stints[0].possessions == 3
    assert stints[0].off_player_ids == tuple(sorted(LINEUP_A_OFF))
    assert stints[0].def_player_ids == tuple(sorted(LINEUP_A_DEF))


def test_build_stints_splits_on_substitution() -> None:
    possessions = pd.DataFrame(
        [
            _possession("G1", 1, 0, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
            _possession("G1", 1, 20, 100, 200, LINEUP_B_OFF, LINEUP_B_DEF, 3),
        ]
    )
    stints = build_stints(possessions)
    assert len(stints) == 2
    assert stints[0].possessions == 1
    assert stints[1].possessions == 1
    assert stints[0].off_player_ids != stints[1].off_player_ids


def test_build_stints_splits_on_new_period() -> None:
    possessions = pd.DataFrame(
        [
            _possession("G1", 1, 700, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
            _possession("G1", 2, 0, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
        ]
    )
    stints = build_stints(possessions)
    assert len(stints) == 2
    assert stints[0].period == 1
    assert stints[1].period == 2


def test_build_stints_splits_on_new_game() -> None:
    possessions = pd.DataFrame(
        [
            _possession("G1", 1, 0, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
            _possession("G2", 1, 0, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
        ]
    )
    stints = build_stints(possessions)
    assert len(stints) == 2
    assert stints[0].game_id == "G1"
    assert stints[1].game_id == "G2"


def test_build_stints_lineup_order_is_irrelevant() -> None:
    """The same set of players in a different array order is still the same lineup."""
    possessions = pd.DataFrame(
        [
            _possession("G1", 1, 0, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
            _possession("G1", 1, 20, 100, 200, list(reversed(LINEUP_A_OFF)), LINEUP_A_DEF, 3),
        ]
    )
    stints = build_stints(possessions)
    assert len(stints) == 1
    assert stints[0].possessions == 2


def test_build_stints_empty_input() -> None:
    assert build_stints(pd.DataFrame()) == []


def test_stints_to_dataframe_round_trip() -> None:
    possessions = pd.DataFrame(
        [
            _possession("G1", 1, 0, 100, 200, LINEUP_A_OFF, LINEUP_A_DEF, 2),
        ]
    )
    df = stints_to_dataframe(build_stints(possessions))
    assert len(df) == 1
    assert df.iloc[0]["points"] == 2
    assert df.iloc[0]["possessions"] == 1
    assert set(df.iloc[0]["off_player_ids"]) == set(LINEUP_A_OFF)
