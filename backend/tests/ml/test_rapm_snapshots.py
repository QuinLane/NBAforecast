"""Snapshot point-in-time / leakage tests for RAPM (rapm.md Prompt 7b) + snapshot plumbing.

The headline test asserts a snapshot for a given ``as_of_date`` only ever uses possessions from
games strictly before that date — the property that keeps a RAPM snapshot leakage-safe when
later consumed as a pre-game feature (feature-engineering.md §2, rapm.md §5). We prove this by
appending a "future" game with a deliberately extreme, easily detectable lineup/point signature
after the cutoff and asserting the computed snapshot is bit-for-bit identical whether or not that
future game is present in the input tables.
"""

from datetime import date

import pandas as pd
from nbaforecast.models.rapm.snapshots import (
    compute_snapshot,
    snapshot_dates,
    snapshot_to_dataframe,
)

PLAYER_IDS = list(range(1, 11))  # 10 players: 5 "known" offense + 5 "known" defense
FUTURE_ONLY_PLAYER = 999  # never appears before the cutoff


def _games(game_ids_and_dates: list[tuple[str, str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"game_id": g, "game_date": d, "season_start_year": y} for g, d, y in game_ids_and_dates]
    )


def _possession_row(game_id: str, points: int, off_ids: list[int], def_ids: list[int]) -> dict:
    return {
        "game_id": game_id,
        "period": 1,
        "start_seconds": 0,
        "offense_team_id": 1,
        "defense_team_id": 2,
        "points": points,
        "off_player_ids": off_ids,
        "def_player_ids": def_ids,
    }


def _base_possessions(n_games: int) -> pd.DataFrame:
    rows = []
    for i in range(n_games):
        for j in range(20):  # 20 possessions/game so stints have real signal
            rows.append(
                _possession_row(
                    f"G{i}",
                    points=2 if j % 3 else 0,
                    off_ids=PLAYER_IDS[:5],
                    def_ids=PLAYER_IDS[5:],
                )
            )
    return pd.DataFrame(rows)


def test_snapshot_ignores_games_on_or_after_cutoff() -> None:
    as_of = date(2024, 1, 10)
    prior_games = _games(
        [(f"G{i}", f"2024-01-0{i + 1}", 2023) for i in range(5)]  # G0..G4, all before cutoff
    )
    prior_possessions = _base_possessions(5)

    # A "future" game dated on the cutoff itself (must be excluded — strictly before only) with
    # an extreme, easily-detectable signature: a brand-new player scoring at an outlandish rate.
    future_game = _games([("G_FUTURE", "2024-01-10", 2023)])
    future_off_ids = [FUTURE_ONLY_PLAYER, 2, 3, 4, 5]
    future_def_ids = [6, 7, 8, 9, 10]
    future_possessions = pd.DataFrame(
        [
            _possession_row("G_FUTURE", points=50, off_ids=future_off_ids, def_ids=future_def_ids)
            for _ in range(20)
        ]
    )

    games_without_future = prior_games
    possessions_without_future = prior_possessions
    games_with_future = pd.concat([prior_games, future_game], ignore_index=True)
    possessions_with_future = pd.concat([prior_possessions, future_possessions], ignore_index=True)

    snapshot_without = compute_snapshot(
        possessions_without_future, games_without_future, as_of_date=as_of
    )
    snapshot_with = compute_snapshot(possessions_with_future, games_with_future, as_of_date=as_of)

    # The future-only player must never appear — proof the future game's possessions were
    # excluded entirely, not merely down-weighted.
    rated_players_without = {r.player_id for r in snapshot_without.ratings}
    rated_players_with = {r.player_id for r in snapshot_with.ratings}
    assert FUTURE_ONLY_PLAYER not in rated_players_without
    assert FUTURE_ONLY_PLAYER not in rated_players_with

    # And the ratings for the shared players are identical whether or not the future game/
    # possessions were present in the input — the future data had zero influence on the fit.
    ratings_without = {r.player_id: (r.orapm, r.drapm) for r in snapshot_without.ratings}
    ratings_with = {r.player_id: (r.orapm, r.drapm) for r in snapshot_with.ratings}
    assert ratings_without == ratings_with


def test_snapshot_restricts_to_rolling_window_seasons() -> None:
    as_of = date(2025, 1, 1)
    games = _games(
        [
            ("G_OLD", "2020-01-01", 2019),  # outside a 3-season window ending at season 2023
            ("G_MID", "2022-01-01", 2021),
            ("G_RECENT", "2023-11-01", 2023),
        ]
    )
    old_off_ids = [101, 2, 3, 4, 5]
    old_def_ids = [6, 7, 8, 9, 10]
    possessions = pd.concat(
        [
            pd.DataFrame(
                [_possession_row("G_OLD", 2, old_off_ids, old_def_ids) for _ in range(20)]
            ),
            pd.DataFrame(
                [_possession_row("G_MID", 2, PLAYER_IDS[:5], PLAYER_IDS[5:]) for _ in range(20)]
            ),
            pd.DataFrame(
                [_possession_row("G_RECENT", 2, PLAYER_IDS[:5], PLAYER_IDS[5:]) for _ in range(20)]
            ),
        ],
        ignore_index=True,
    )

    snapshot = compute_snapshot(possessions, games, as_of_date=as_of, window_seasons=3)
    rated_players = {r.player_id for r in snapshot.ratings}
    assert 101 not in rated_players  # G_OLD's unique player excluded by the window


def test_compute_snapshot_empty_history_returns_empty_snapshot() -> None:
    snapshot = compute_snapshot(pd.DataFrame(), pd.DataFrame(), as_of_date=date(2024, 1, 1))
    assert snapshot.ratings == []


def test_snapshot_to_dataframe_shape() -> None:
    as_of = date(2024, 1, 10)
    games = _games([(f"G{i}", f"2024-01-0{i + 1}", 2023) for i in range(5)])
    possessions = _base_possessions(5)
    snapshot = compute_snapshot(possessions, games, as_of_date=as_of)

    rows = snapshot_to_dataframe(snapshot)
    assert set(rows.columns) == {
        "player_id",
        "as_of_date",
        "window",
        "orapm",
        "drapm",
        "rapm",
        "possessions",
    }
    assert (rows["as_of_date"] == as_of).all()
    assert (rows["window"] == 3).all()
    assert (rows["rapm"] == rows["orapm"] + rows["drapm"]).all()


def test_snapshot_dates_includes_day_after_season_end() -> None:
    games = _games(
        [
            ("G1", "2023-10-24", 2023),
            ("G2", "2024-04-14", 2023),
        ]
    )
    dates = snapshot_dates(games, monthly=False)
    assert date(2024, 4, 15) in dates
