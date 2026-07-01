"""Ridge fit + temporal λ cross-validation — rapm.md Prompt 3 / §2-3.

``fit_rapm`` solves the weighted ridge problem ``minimize ||y - Xβ||²_w + λ||β||²`` over the
sparse design matrix from ``design.py``, using ``sklearn.linear_model.Ridge`` with a
sparse-compatible solver. The fitted coefficients are read back off via the design matrix's
``PlayerIndex`` into per-player ORAPM (offense coefficient), DRAPM (defense coefficient), and
RAPM (their sum) — all "points per 100 possessions" rates.

``select_alpha`` cross-validates λ **temporally**: candidate values are scored by how well
ratings fit on an earlier slice of games *retrodict* a later, held-out slice (grouped by
``game_id``, never split mid-game), rather than a random/shuffled split — a random split would
leak information about a stint's own game into training (rapm.md §3).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from nbaforecast.models.rapm.design import RapmDesignMatrix, build_design_matrix

DEFAULT_ALPHA_GRID: tuple[float, ...] = (100.0, 500.0, 1_000.0, 2_000.0, 5_000.0, 10_000.0)
_RIDGE_SOLVER = "sparse_cg"


@dataclass(slots=True)
class PlayerRapmRating:
    """One player's fitted RAPM rating for a window (points per 100 possessions)."""

    player_id: int
    orapm: float
    drapm: float
    rapm: float


@dataclass(slots=True)
class RapmFitResult:
    """A fitted ridge model plus its per-player ratings and the λ used."""

    model: Ridge
    alpha: float
    ratings: list[PlayerRapmRating]


def fit_rapm(design: RapmDesignMatrix, alpha: float) -> RapmFitResult:
    """Fit weighted ridge regression on ``design`` at a fixed ``alpha`` (λ).

    Args:
        design: Output of :func:`build_design_matrix`.
        alpha: Ridge regularization strength (λ). Larger shrinks coefficients harder toward zero.

    Returns:
        The fitted sklearn ``Ridge`` model and per-player ORAPM/DRAPM/RAPM ratings.
    """
    model = Ridge(alpha=alpha, fit_intercept=True, solver=_RIDGE_SOLVER)
    model.fit(design.x, design.y, sample_weight=design.weights)

    coefficients = np.asarray(model.coef_)
    ratings = [
        PlayerRapmRating(
            player_id=player_id,
            orapm=float(coefficients[design.player_index.offense_column(player_id)]),
            drapm=float(coefficients[design.player_index.defense_column(player_id)]),
            rapm=float(
                coefficients[design.player_index.offense_column(player_id)]
                + coefficients[design.player_index.defense_column(player_id)]
            ),
        )
        for player_id in design.player_index.player_ids
    ]
    return RapmFitResult(model=model, alpha=alpha, ratings=ratings)


def _retrodiction_rmse(
    train_stints: pd.DataFrame, holdout_stints: pd.DataFrame, alpha: float
) -> float | None:
    """Fit on ``train_stints``, score retrodiction RMSE of per-100-poss margins on
    ``holdout_stints``. Returns ``None`` if either split is empty or has no overlapping players
    to score (nothing usable to retrodict)."""
    if train_stints.empty or holdout_stints.empty:
        return None

    train_design = build_design_matrix(train_stints)
    if train_design.x.shape[0] == 0 or train_design.x.shape[1] == 0:
        return None
    fit_result = fit_rapm(train_design, alpha)
    rating_by_player = {r.player_id: r for r in fit_result.ratings}

    predicted = np.empty(len(holdout_stints))
    actual = np.empty(len(holdout_stints))
    for i, record in enumerate(holdout_stints.to_dict("records")):
        off_rapm = sum(
            rating_by_player[int(p)].orapm
            for p in record["off_player_ids"]
            if int(p) in rating_by_player
        )
        def_rapm = sum(
            rating_by_player[int(p)].drapm
            for p in record["def_player_ids"]
            if int(p) in rating_by_player
        )
        predicted[i] = float(fit_result.model.intercept_) + off_rapm + def_rapm
        actual[i] = (int(record["points"]) / int(record["possessions"])) * 100.0

    return float(np.sqrt(np.mean((predicted - actual) ** 2)))


def select_alpha(
    stints: pd.DataFrame,
    *,
    alpha_grid: tuple[float, ...] = DEFAULT_ALPHA_GRID,
    n_splits: int = 3,
) -> float:
    """Temporally cross-validate λ by retrodiction RMSE; return the minimizing value.

    Splits ``stints`` into ``n_splits`` chronological folds by ``game_id`` order (never
    shuffled — a shuffled/random split would let a stint's own game leak into the training fold
    via near-duplicate lineups from the same game, and more fundamentally would defeat the point
    of testing *forward* predictive power). For each split point, everything before is the
    training fold and everything after (up to the next split) is the held-out fold; RMSE is
    averaged across folds for each candidate ``alpha``.

    Falls back to the middle of ``alpha_grid`` if there isn't enough chronological spread to form
    at least one train/holdout pair (e.g. all stints from a single game).
    """
    game_order = list(dict.fromkeys(stints["game_id"]))  # first-seen order, de-duplicated
    if len(game_order) < 2:
        return alpha_grid[len(alpha_grid) // 2]

    fold_edges = np.linspace(0, len(game_order), n_splits + 1, dtype=int)[1:-1]
    split_points = sorted({int(e) for e in fold_edges if 0 < e < len(game_order)})
    if not split_points:
        split_points = [len(game_order) // 2]

    best_alpha = alpha_grid[0]
    best_rmse = np.inf
    for alpha in alpha_grid:
        fold_rmses: list[float] = []
        for split in split_points:
            train_games = set(game_order[:split])
            holdout_games = set(game_order[split:])
            train_stints = stints[stints["game_id"].isin(train_games)]
            holdout_stints = stints[stints["game_id"].isin(holdout_games)]
            rmse = _retrodiction_rmse(train_stints, holdout_stints, alpha)
            if rmse is not None:
                fold_rmses.append(rmse)
        if not fold_rmses:
            continue
        mean_rmse = float(np.mean(fold_rmses))
        if mean_rmse < best_rmse:
            best_rmse = mean_rmse
            best_alpha = alpha

    return best_alpha
