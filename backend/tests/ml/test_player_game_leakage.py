"""No-leakage and train/serve-parity regression tests for player-game features
(feature-engineering.md Prompt 6, mirroring ``test_feature_leakage.py`` for team-game).

Uses the larger synthetic multi-team, multi-season player league (not the tiny hand-derived
fixture in ``test_player_game.py``) and checks two structural properties for *every* feature:

(a) **No-leakage** — recomputing a sampled game's features from a dataset truncated to end at
    that game must reproduce the materialized (full-history) row exactly.
(b) **Train/serve parity** — calling ``build_player_game_features`` with ``as_of`` set to a
    sampled game's date, against a dataset that only knows about *prior* results, must reproduce
    that game's materialized training row exactly.
"""

import pandas as pd
import pytest
from nbaforecast.features.player_game import FEATURE_COLUMNS, build_player_game_features

from tests.ml._synthetic_player_league import build_synthetic_player_league

SEASONS = (("2021-22", 2021), ("2022-23", 2022), ("2023-24", 2023))


def _sample_game_ids(games: pd.DataFrame) -> list[str]:
    """A handful of games spread across the league: early (mostly-NaN features), mid-season,
    a season-boundary game, and the very last game (no future data exists at all)."""
    ordered = games.sort_values("game_date")["game_id"].tolist()
    n = len(ordered)
    return [ordered[1], ordered[n // 4], ordered[n // 2], ordered[-1]]


@pytest.fixture(scope="module")
def league() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return build_synthetic_player_league(n_teams=6, seasons=SEASONS)


@pytest.fixture(scope="module")
def materialized(
    league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> pd.DataFrame:
    games, team_game_stats, _teams, player_game_stats, players = league
    return build_player_game_features(games, player_game_stats, team_game_stats, players)


def _assert_player_row_matches(
    candidate: pd.DataFrame, materialized: pd.DataFrame, game_id: str, player_id: int
) -> None:
    candidate_row = candidate.loc[
        (candidate["game_id"] == game_id) & (candidate["player_id"] == player_id)
    ].iloc[0]
    materialized_row = materialized.loc[
        (materialized["game_id"] == game_id) & (materialized["player_id"] == player_id)
    ].iloc[0]
    pd.testing.assert_series_equal(
        candidate_row[FEATURE_COLUMNS],
        materialized_row[FEATURE_COLUMNS],
        check_dtype=False,
        check_names=False,
    )


@pytest.mark.parametrize("game_index", [0, 1, 2, 3])
def test_no_leakage_recompute_from_truncated_history(
    league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame],
    materialized: pd.DataFrame,
    game_index: int,
) -> None:
    games, team_game_stats, _teams, player_game_stats, players = league
    sample_game_id = _sample_game_ids(games)[game_index]
    cutoff = games.loc[games["game_id"] == sample_game_id, "game_date"].iloc[0]

    # Drop every game dated after the sample — if any feature secretly depended on future data,
    # this recompute would diverge from the materialized (full-history) row.
    truncated_games = games.loc[games["game_date"] <= cutoff]
    truncated_ids = truncated_games["game_id"]
    truncated_team_stats = team_game_stats.loc[team_game_stats["game_id"].isin(truncated_ids)]
    truncated_player_stats = player_game_stats.loc[player_game_stats["game_id"].isin(truncated_ids)]
    recomputed = build_player_game_features(
        truncated_games, truncated_player_stats, truncated_team_stats, players
    )

    sample_players = player_game_stats.loc[
        player_game_stats["game_id"] == sample_game_id, "player_id"
    ].unique()
    for player_id in sample_players:
        _assert_player_row_matches(recomputed, materialized, sample_game_id, player_id)


@pytest.mark.parametrize("game_index", [0, 1, 2, 3])
def test_train_serve_parity_at_tip_off(
    league: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame],
    materialized: pd.DataFrame,
    game_index: int,
) -> None:
    games, team_game_stats, _teams, player_game_stats, players = league
    sample_game_id = _sample_game_ids(games)[game_index]
    tip_off = games.loc[games["game_id"] == sample_game_id, "game_date"].iloc[0]

    # Simulate "tonight, before the game": prior completed games + this one game re-marked
    # scheduled, with its own box scores withheld entirely.
    prior_games = games.loc[games["game_date"] < tip_off]
    sample_game = games.loc[games["game_id"] == sample_game_id].copy()
    sample_game["status"] = "scheduled"
    serving_games = pd.concat([prior_games, sample_game], ignore_index=True)
    prior_ids = prior_games["game_id"]
    prior_team_stats = team_game_stats.loc[team_game_stats["game_id"].isin(prior_ids)]
    prior_player_stats = player_game_stats.loc[player_game_stats["game_id"].isin(prior_ids)]

    serving = build_player_game_features(
        serving_games,
        prior_player_stats,
        prior_team_stats,
        players,
        as_of=tip_off.date(),
    )

    # A player whose *team* has no completed game before tip-off can't be inferred onto tonight's
    # serving slate (build_player_game_features._scheduled_player_rows's own documented
    # limitation — a roster has to come from *somewhere*, and there's no roster table here, only
    # "most recently observed team"); skip those, matching team_game.py's analogous "no history ->
    # no serving row" behavior for a team's very first game.
    known_teams = set(prior_player_stats["team_id"].unique())
    sample_players = player_game_stats.loc[
        (player_game_stats["game_id"] == sample_game_id)
        & (player_game_stats["team_id"].isin(known_teams)),
        "player_id",
    ].unique()
    for player_id in sample_players:
        _assert_player_row_matches(serving, materialized, sample_game_id, player_id)
