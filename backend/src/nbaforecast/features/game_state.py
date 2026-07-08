"""In-game state features for the live/replay win-probability head (roadmap M3.9).

One row per play-by-play event, from the **home team's perspective**: the score margin, the time
left in the game, and the period. These are the inputs a win-probability model needs to answer
"given the game is in *this* state, how likely is the home team to win?" — the substrate for the
game-page win-probability timeline. Everything here is known *at that moment* of the game, so there
is no leakage of the final outcome into the features (the outcome is only ever the label).
"""

import numpy as np
import pandas as pd

GAME_STATE_FEATURE_COLUMNS: tuple[str, ...] = ("score_margin", "seconds_remaining", "period")

REGULATION_PERIODS = 4
PERIOD_SECONDS = 12 * 60  # a regulation quarter
OT_SECONDS = 5 * 60  # an overtime period


def seconds_remaining(period: pd.Series, seconds_left_in_period: pd.Series) -> pd.Series:
    """Seconds left in the game given the period and seconds left in the current period.

    Regulation: add the full periods still to come. Overtime (period > 4): just the time left in
    the current OT — win probability there is dominated by the margin anyway, and modelling a
    hypothetical *next* OT would be speculative.
    """
    regulation = seconds_left_in_period + (REGULATION_PERIODS - period) * PERIOD_SECONDS
    return pd.Series(
        np.where(period <= REGULATION_PERIODS, regulation, seconds_left_in_period),
        index=period.index,
    )


def build_game_state_features(games: pd.DataFrame, play_by_play: pd.DataFrame) -> pd.DataFrame:
    """One home-perspective feature row per usable play-by-play event.

    Rows without a running score or clock (some non-scoring markers) are dropped — the game state
    is undefined for them. ``game_date``/``season_start_year`` ride along for walk-forward folds.
    """
    usable = play_by_play.dropna(
        subset=["home_score", "away_score", "seconds_remaining_period", "period"]
    ).copy()
    usable = usable.merge(
        games[["game_id", "game_date", "season_start_year"]], on="game_id", how="inner"
    )
    usable["score_margin"] = (usable["home_score"] - usable["away_score"]).astype(float)
    usable["seconds_remaining"] = seconds_remaining(
        usable["period"], usable["seconds_remaining_period"]
    ).astype(float)
    usable["period"] = usable["period"].astype(float)
    return usable[
        [
            "game_id",
            "event_num",
            "game_date",
            "season_start_year",
            "home_score",
            "away_score",
            *GAME_STATE_FEATURE_COLUMNS,
        ]
    ].reset_index(drop=True)


def in_game_win_labels(features: pd.DataFrame, games: pd.DataFrame) -> pd.Series:
    """Home-won (1.0/0.0) for each feature row, from that game's final score.

    The label is the same for every event of a game — the model learns how the *state* maps to
    that eventual outcome. ``NaN`` for games without a final score (skipped by the trainer).
    """
    finals = games.assign(
        home_won=np.where(
            games["home_score"].notna() & games["away_score"].notna(),
            (games["home_score"] > games["away_score"]).astype(float),
            np.nan,
        )
    )
    merged = features[["game_id"]].merge(finals[["game_id", "home_won"]], on="game_id", how="left")
    merged.index = features.index
    return merged["home_won"]
