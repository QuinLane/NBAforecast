"""Unit tests for leakage-safe primitives (feature-engineering.md Prompt 1).

Every test here is ultimately a no-leakage test: each primitive's output for a row must depend
only on rows strictly before it (by ``datetime_col``) within its group, never on the row itself
or anything later.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.primitives import (
    as_of_join,
    days_rest,
    rolling_as_of,
    schedule_density,
    travel_distance,
)


def _team_games(values: list[float], dates: list[str], team: str = "A") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team_id": [team] * len(values),
            "game_date": pd.to_datetime(dates),
            "value": values,
        }
    )


# ── rolling_as_of ────────────────────────────────────────────────────────────────────────────


def test_rolling_as_of_excludes_current_row() -> None:
    dates = ["2024-01-01", "2024-01-03", "2024-01-05", "2024-01-07"]
    df = _team_games([10.0, 20.0, 30.0, 40.0], dates)
    out = rolling_as_of(df, "team_id", "value", window=2, datetime_col="game_date")

    assert np.isnan(out.iloc[0])  # no prior games
    assert out.iloc[1] == 10.0  # only game 1 is prior
    assert out.iloc[2] == 15.0  # mean(10, 20)
    assert out.iloc[3] == 25.0  # mean(20, 30) — window=2, excludes game 4 itself


def test_rolling_as_of_unaffected_by_future_or_current_value() -> None:
    dates = ["2024-01-01", "2024-01-03", "2024-01-05", "2024-01-07"]
    base = _team_games([10.0, 20.0, 30.0, 40.0], dates)
    # Mutate row 2 (current, relative to the assertion below) and row 3 (future).
    mutated = _team_games([10.0, 20.0, 999.0, -999.0], dates)

    out_base = rolling_as_of(base, "team_id", "value", window=10, datetime_col="game_date")
    out_mutated = rolling_as_of(mutated, "team_id", "value", window=10, datetime_col="game_date")

    # Row 2's own feature (computed from rows before it) is identical whether or not row 2's own
    # value, or any later row's value, changes.
    assert out_base.iloc[2] == out_mutated.iloc[2] == 15.0


def test_rolling_as_of_respects_group_keys() -> None:
    a = _team_games([10.0, 20.0], ["2024-01-01", "2024-01-03"], team="A")
    b = _team_games([100.0, 200.0], ["2024-01-02", "2024-01-04"], team="B")
    df = pd.concat([a, b], ignore_index=True)
    out = rolling_as_of(df, "team_id", "value", window=5, datetime_col="game_date")

    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 10.0  # team A's prior game only, never team B's
    assert np.isnan(out.iloc[2])
    assert out.iloc[3] == 100.0


# ── as_of_join ───────────────────────────────────────────────────────────────────────────────


def test_as_of_join_only_matches_strictly_prior_right_rows() -> None:
    left = pd.DataFrame({"team_id": ["A"], "game_date": pd.to_datetime(["2024-01-10"])})
    right = pd.DataFrame(
        {
            "team_id": ["A", "A", "A"],
            "game_date": pd.to_datetime(["2024-01-05", "2024-01-10", "2024-01-15"]),
            "elo": [1500.0, 1600.0, 1700.0],
        }
    )
    out = as_of_join(left, right, on="team_id", datetime_col="game_date")

    # The exact-date row (elo=1600) and the future row (elo=1700) must never be picked.
    assert out.loc[0, "elo"] == 1500.0


def test_as_of_join_allow_exact_matches_opt_in() -> None:
    left = pd.DataFrame({"team_id": ["A"], "game_date": pd.to_datetime(["2024-01-10"])})
    right = pd.DataFrame(
        {"team_id": ["A"], "game_date": pd.to_datetime(["2024-01-10"]), "elo": [1600.0]}
    )
    strict = as_of_join(left, right, on="team_id", datetime_col="game_date")
    lenient = as_of_join(
        left, right, on="team_id", datetime_col="game_date", allow_exact_matches=True
    )

    assert np.isnan(strict.loc[0, "elo"])
    assert lenient.loc[0, "elo"] == 1600.0


def test_as_of_join_no_future_row_for_any_group() -> None:
    left = pd.DataFrame(
        {"team_id": ["A", "B"], "game_date": pd.to_datetime(["2024-01-10", "2024-01-10"])}
    )
    right = pd.DataFrame(
        {
            "team_id": ["A", "B"],
            "game_date": pd.to_datetime(["2024-02-01", "2024-01-01"]),  # A's row is in the future
            "elo": [9999.0, 1400.0],
        }
    )
    out = as_of_join(left, right, on="team_id", datetime_col="game_date")

    assert np.isnan(out.loc[out["team_id"] == "A", "elo"].iloc[0])
    assert out.loc[out["team_id"] == "B", "elo"].iloc[0] == 1400.0


# ── days_rest ────────────────────────────────────────────────────────────────────────────────


def test_days_rest_matches_manual_diff() -> None:
    df = _team_games([0, 0, 0], ["2024-01-01", "2024-01-03", "2024-01-04"])
    out = days_rest(df, "team_id", "game_date")

    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 2
    assert out.iloc[2] == 1


# ── schedule_density ─────────────────────────────────────────────────────────────────────────


def test_schedule_density_counts_prior_games_in_window() -> None:
    # Games on day 0, 2, 5, 6, 9 (relative). 7-day window as of each game.
    dates = ["2024-01-01", "2024-01-03", "2024-01-06", "2024-01-07", "2024-01-10"]
    df = _team_games([0, 0, 0, 0, 0], dates)
    out = schedule_density(df, "team_id", "game_date", window_days=7)

    assert out.iloc[0] == 0  # no prior games
    assert out.iloc[1] == 1  # just game 0 (2 days prior)
    assert out.iloc[2] == 2  # games 0, 1 (5 and 3 days prior)
    assert out.iloc[3] == 3  # games 0, 1, 2 (6, 4, 1 days prior)
    # games 2, 3 (4, 3 days prior); game 1 is exactly 7 days prior — boundary is exclusive;
    # game 0 is 9 days prior — outside the window.
    assert out.iloc[4] == 2


def test_schedule_density_excludes_current_row() -> None:
    df = _team_games([0], ["2024-01-01"])
    out = schedule_density(df, "team_id", "game_date", window_days=7)
    assert out.iloc[0] == 0


# ── travel_distance ──────────────────────────────────────────────────────────────────────────


def test_travel_distance_known_haversine_distance() -> None:
    # LA (34.05, -118.24) -> NYC (40.71, -74.01), well-known ~3936 km great-circle distance.
    df = pd.DataFrame(
        {
            "team_id": ["A", "A"],
            "game_date": pd.to_datetime(["2024-01-01", "2024-01-03"]),
            "lat": [34.05, 40.71],
            "lon": [-118.24, -74.01],
        }
    )
    out = travel_distance(df, "team_id", lat_col="lat", lon_col="lon", datetime_col="game_date")

    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == pytest.approx(3936, rel=0.01)


def test_travel_distance_zero_for_same_location() -> None:
    df = pd.DataFrame(
        {
            "team_id": ["A", "A"],
            "game_date": pd.to_datetime(["2024-01-01", "2024-01-03"]),
            "lat": [34.05, 34.05],
            "lon": [-118.24, -118.24],
        }
    )
    out = travel_distance(df, "team_id", lat_col="lat", lon_col="lon", datetime_col="game_date")
    assert out.iloc[1] == pytest.approx(0.0, abs=1e-6)
