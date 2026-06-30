"""No-leakage and train/serve-parity regression tests (feature-engineering.md Prompt 6).

Builds a larger synthetic multi-team, multi-season league (not the tiny hand-derived fixture in
test_team_game.py) and checks two structural properties that must hold for *every* feature, not
just the handful a value-level unit test happens to assert on:

(a) **No-leakage** — recomputing a sampled game's features from a dataset truncated to end at
    that game must reproduce the materialized (full-history) row exactly. If it didn't, some
    feature would have to be reading a row dated after the game it's predicting.
(b) **Train/serve parity** — calling ``build_team_game_features`` with ``as_of`` set to a sampled
    game's date, against a dataset that only knows about *prior* results, must reproduce that
    game's materialized training row exactly. Training and serving are one code path by
    construction (team_game.py's module docstring); this is the proof.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.features.team_game import FEATURE_COLUMNS, build_team_game_features

N_TEAMS = 6
_SEASONS = (("2022-23", 2022), ("2023-24", 2023))


def _build_league() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A deterministic round-robin league: every team plays every other team home + away, each
    of 2 seasons — enough games/teams/seasons to exercise rolling windows, season-to-date resets,
    and head-to-head beyond what the small hand-picked T2.2 fixture covers.
    """
    rng = np.random.default_rng(42)
    team_ids = list(range(1, N_TEAMS + 1))
    teams = pd.DataFrame(
        {
            "team_id": team_ids,
            "arena_lat": rng.uniform(25, 47, N_TEAMS),
            "arena_lon": rng.uniform(-122, -71, N_TEAMS),
        }
    )

    games_rows: list[dict[str, object]] = []
    stats_rows: list[dict[str, object]] = []
    game_counter = 0
    for season, season_start_year in _SEASONS:
        game_date = pd.Timestamp(f"{season_start_year}-10-20")
        for home in team_ids:
            for away in team_ids:
                if home == away:
                    continue
                game_counter += 1
                game_id = f"G{game_counter}"
                game_date = game_date + pd.Timedelta(2, unit="D")
                home_net = float(rng.normal(home - away, 5))
                pace = float(rng.normal(98, 3))
                games_rows.append(
                    {
                        "game_id": game_id,
                        "season": season,
                        "season_start_year": season_start_year,
                        "game_date": game_date,
                        "home_team_id": home,
                        "away_team_id": away,
                        "home_score": round(100 + home_net),
                        "away_score": round(100 - home_net),
                        "status": "final",
                    }
                )
                stats_rows.append(
                    {
                        "game_id": game_id,
                        "team_id": home,
                        "opponent_team_id": away,
                        "is_home": True,
                        "off_rating": 110 + home_net / 2,
                        "def_rating": 110 - home_net / 2,
                        "net_rating": home_net,
                        "pace": pace,
                    }
                )
                stats_rows.append(
                    {
                        "game_id": game_id,
                        "team_id": away,
                        "opponent_team_id": home,
                        "is_home": False,
                        "off_rating": 110 - home_net / 2,
                        "def_rating": 110 + home_net / 2,
                        "net_rating": -home_net,
                        "pace": pace,
                    }
                )
    return pd.DataFrame(games_rows), pd.DataFrame(stats_rows), teams


def _sample_game_ids(games: pd.DataFrame) -> list[str]:
    """A handful of games spread across the league: early (mostly-NaN features), mid-season,
    a season-boundary game, and the very last game (no future data exists at all)."""
    ordered = games.sort_values("game_date")["game_id"].tolist()
    n = len(ordered)
    return [ordered[1], ordered[n // 4], ordered[n // 2], ordered[-1]]


@pytest.fixture(scope="module")
def league() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _build_league()


@pytest.fixture(scope="module")
def materialized(league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> pd.DataFrame:
    games, team_game_stats, teams = league
    return build_team_game_features(games, team_game_stats, teams)


def _assert_team_row_matches(
    candidate: pd.DataFrame, materialized: pd.DataFrame, game_id: str, team_id: int
) -> None:
    candidate_row = candidate.loc[
        (candidate["game_id"] == game_id) & (candidate["team_id"] == team_id)
    ].iloc[0]
    materialized_row = materialized.loc[
        (materialized["game_id"] == game_id) & (materialized["team_id"] == team_id)
    ].iloc[0]
    pd.testing.assert_series_equal(
        candidate_row[FEATURE_COLUMNS],
        materialized_row[FEATURE_COLUMNS],
        check_dtype=False,
        check_names=False,
    )


@pytest.mark.parametrize("game_index", [0, 1, 2, 3])
def test_no_leakage_recompute_from_truncated_history(
    league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    materialized: pd.DataFrame,
    game_index: int,
) -> None:
    games, team_game_stats, teams = league
    sample_game_id = _sample_game_ids(games)[game_index]
    cutoff = games.loc[games["game_id"] == sample_game_id, "game_date"].iloc[0]

    # Drop every game dated after the sample — if any feature secretly depended on future data,
    # this recompute would diverge from the materialized (full-history) row.
    truncated_games = games.loc[games["game_date"] <= cutoff]
    truncated_stats = team_game_stats.loc[
        team_game_stats["game_id"].isin(truncated_games["game_id"])
    ]
    recomputed = build_team_game_features(truncated_games, truncated_stats, teams)

    sample_game = games.loc[games["game_id"] == sample_game_id].iloc[0]
    for team_id in (sample_game["home_team_id"], sample_game["away_team_id"]):
        _assert_team_row_matches(recomputed, materialized, sample_game_id, team_id)


@pytest.mark.parametrize("game_index", [0, 1, 2, 3])
def test_train_serve_parity_at_tip_off(
    league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    materialized: pd.DataFrame,
    game_index: int,
) -> None:
    games, team_game_stats, teams = league
    sample_game_id = _sample_game_ids(games)[game_index]
    tip_off = games.loc[games["game_id"] == sample_game_id, "game_date"].iloc[0]

    # Simulate "tonight, before the game": prior completed games + this one game re-marked
    # scheduled, with its own result withheld entirely.
    prior_games = games.loc[games["game_date"] < tip_off]
    sample_game = games.loc[games["game_id"] == sample_game_id].copy()
    sample_game["status"] = "scheduled"
    serving_games = pd.concat([prior_games, sample_game], ignore_index=True)
    prior_stats = team_game_stats.loc[team_game_stats["game_id"].isin(prior_games["game_id"])]

    serving = build_team_game_features(serving_games, prior_stats, teams, as_of=tip_off.date())

    sample_game_row = games.loc[games["game_id"] == sample_game_id].iloc[0]
    for team_id in (sample_game_row["home_team_id"], sample_game_row["away_team_id"]):
        _assert_team_row_matches(serving, materialized, sample_game_id, team_id)
