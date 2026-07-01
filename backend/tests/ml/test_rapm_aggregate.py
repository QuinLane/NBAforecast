"""Leakage + correctness tests for RAPM→feature aggregation (rapm.md Prompt 6/7 + T3.9).

Two properties matter (feature-engineering.md §2/§5):
  * **Leakage-safety** — a game's RAPM feature only ever comes from a snapshot dated on or before
    that game; a snapshot dated *after* the game is never used, and prior rosters never include a
    game's own participants.
  * **Correctness** — the team aggregate is the possession-weighted mean of its prior roster's
    per-player RAPM, and the player feature is that player's latest pre-game RAPM.
"""

from datetime import date

import numpy as np
import pandas as pd
from nbaforecast.models.rapm.aggregate import (
    attach_player_rapm,
    attach_team_rapm,
    prior_rosters,
)

WINDOW = 3


def _snapshots(rows: list[tuple[int, date, float, float, int]]) -> pd.DataFrame:
    """rows: (player_id, as_of_date, orapm, drapm, possessions) — rapm = orapm + drapm."""
    return pd.DataFrame(
        [
            {
                "player_id": pid,
                "as_of_date": as_of,
                "window": WINDOW,
                "orapm": orapm,
                "drapm": drapm,
                "rapm": orapm + drapm,
                "possessions": poss,
            }
            for pid, as_of, orapm, drapm, poss in rows
        ]
    )


# ── attach_player_rapm ────────────────────────────────────────────────────────────────────────


def test_player_rapm_uses_latest_snapshot_on_or_before_game() -> None:
    snapshots = _snapshots(
        [
            (1, date(2023, 1, 1), 2.0, 1.0, 500),
            (1, date(2023, 2, 1), 4.0, 1.0, 600),  # the latest one <= game_date
            (1, date(2023, 4, 1), 9.0, 9.0, 700),  # AFTER the game — must be ignored (leakage)
        ]
    )
    keys = pd.DataFrame([{"player_id": 1, "game_date": date(2023, 3, 15)}])

    result = attach_player_rapm(keys, snapshots, window=WINDOW)

    assert result.iloc[0] == 5.0  # 4.0 + 1.0 from the 2023-02-01 snapshot, not the future one


def test_player_rapm_is_nan_before_any_snapshot() -> None:
    snapshots = _snapshots([(1, date(2023, 2, 1), 4.0, 1.0, 600)])
    keys = pd.DataFrame([{"player_id": 1, "game_date": date(2023, 1, 1)}])

    result = attach_player_rapm(keys, snapshots, window=WINDOW)

    assert np.isnan(result.iloc[0])


def test_player_rapm_preserves_row_order_and_index() -> None:
    snapshots = _snapshots(
        [
            (1, date(2023, 1, 1), 1.0, 0.0, 100),
            (2, date(2023, 1, 1), 5.0, 0.0, 100),
        ]
    )
    keys = pd.DataFrame(
        [
            {"player_id": 2, "game_date": date(2023, 6, 1)},
            {"player_id": 1, "game_date": date(2023, 6, 1)},
        ],
        index=[10, 20],
    )

    result = attach_player_rapm(keys, snapshots, window=WINDOW)

    assert list(result.index) == [10, 20]
    assert result.loc[10] == 5.0  # player 2 first
    assert result.loc[20] == 1.0  # player 1 second


# ── prior_rosters ─────────────────────────────────────────────────────────────────────────────


def _games(rows: list[tuple[str, int, date]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"game_id": g, "season_start_year": y, "game_date": d} for g, y, d in rows]
    )


def _pgs(rows: list[tuple[str, int, int]]) -> pd.DataFrame:
    return pd.DataFrame([{"game_id": g, "team_id": t, "player_id": p} for g, t, p in rows])


def test_prior_roster_excludes_current_and_future_games() -> None:
    games = _games(
        [
            ("G1", 2023, date(2023, 10, 1)),
            ("G2", 2023, date(2023, 10, 3)),
            ("G3", 2023, date(2023, 10, 5)),
        ]
    )
    pgs = _pgs(
        [
            ("G1", 100, 1),
            ("G1", 100, 2),
            ("G2", 100, 3),  # new player debuts in G2
            ("G3", 100, 4),  # G3's own participant — must NOT appear in G3's prior roster
        ]
    )

    rosters = prior_rosters(pgs, games)
    by_game = {g: set(grp["player_id"]) for g, grp in rosters.groupby("game_id")}

    assert "G1" not in by_game  # first game of the season has no prior roster
    assert by_game["G2"] == {1, 2}  # only G1's players
    assert by_game["G3"] == {1, 2, 3}  # G1 + G2, never player 4 (G3's own)


def test_prior_roster_is_season_scoped() -> None:
    games = _games(
        [
            ("A", 2022, date(2023, 3, 1)),
            ("B", 2023, date(2023, 10, 1)),  # next season — must not inherit last season's roster
            ("C", 2023, date(2023, 10, 3)),
        ]
    )
    pgs = _pgs([("A", 100, 1), ("B", 100, 2), ("C", 100, 3)])

    rosters = prior_rosters(pgs, games)
    by_game = {g: set(grp["player_id"]) for g, grp in rosters.groupby("game_id")}

    assert "B" not in by_game  # first game of 2023 season: no prior roster despite 2022 history
    assert by_game["C"] == {2}  # only B (same season), not A (prior season)


# ── attach_team_rapm ──────────────────────────────────────────────────────────────────────────


def test_team_rapm_is_possession_weighted_over_prior_roster() -> None:
    games = _games(
        [
            ("G1", 2023, date(2023, 10, 1)),
            ("G2", 2023, date(2023, 10, 3)),
        ]
    )
    pgs = _pgs([("G1", 100, 1), ("G1", 100, 2), ("G2", 100, 1), ("G2", 100, 2)])
    # G2's prior roster = {1, 2}. Snapshots dated before G2:
    snapshots = _snapshots(
        [
            (1, date(2023, 9, 1), 6.0, 2.0, 300),
            (2, date(2023, 9, 1), 2.0, 0.0, 100),
        ]
    )
    team_keys = pd.DataFrame([{"game_id": "G2", "team_id": 100}])

    result = attach_team_rapm(team_keys, pgs, games, snapshots, window=WINDOW)

    # possession-weighted: (6*300 + 2*100) / 400 = 5.0 ; (2*300 + 0*100)/400 = 1.5
    assert result["team_orapm"].iloc[0] == 5.0
    assert result["team_drapm"].iloc[0] == 1.5


def test_team_rapm_ignores_future_snapshot() -> None:
    games = _games([("G1", 2023, date(2023, 10, 1)), ("G2", 2023, date(2023, 10, 3))])
    pgs = _pgs([("G1", 100, 1), ("G2", 100, 1)])
    snapshots = _snapshots(
        [
            (1, date(2023, 9, 1), 3.0, 1.0, 200),
            (1, date(2023, 11, 1), 50.0, 50.0, 999),  # after G2 — leakage if used
        ]
    )
    team_keys = pd.DataFrame([{"game_id": "G2", "team_id": 100}])

    result = attach_team_rapm(team_keys, pgs, games, snapshots, window=WINDOW)

    assert result["team_orapm"].iloc[0] == 3.0
    assert result["team_drapm"].iloc[0] == 1.0


def test_team_rapm_nan_for_first_game_of_season() -> None:
    games = _games([("G1", 2023, date(2023, 10, 1))])
    pgs = _pgs([("G1", 100, 1)])
    snapshots = _snapshots([(1, date(2023, 9, 1), 3.0, 1.0, 200)])
    team_keys = pd.DataFrame([{"game_id": "G1", "team_id": 100}])

    result = attach_team_rapm(team_keys, pgs, games, snapshots, window=WINDOW)

    assert np.isnan(result["team_orapm"].iloc[0])
    assert np.isnan(result["team_drapm"].iloc[0])
