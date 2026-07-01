"""Correctness + λ-selection tests for RAPM ridge fitting (rapm.md Prompt 3 / Prompt 7a).

The correctness test builds a tiny synthetic league where each player has a **known true
offensive/defensive effect** baked directly into each stint's simulated point total, lineups are
randomized every stint so no two players are perfectly collinear, and asserts that ridge at a
small ``alpha`` recovers each player's true RAPM within a tight tolerance — this is the textbook
validation for an APM/RAPM implementation (rapm.md §7 Prompt 7a).

Each synthetic stint is given a large possession count (``STINT_POSSESSIONS``) so its *true*
per-100-possession rate is reproduced by an integer point total with only negligible rounding
error — mirroring the real ``possessions`` table, where individual possessions always score an
integer (0/1/2/3) but a stint's *rate* is fractional only through aggregation.
"""

import numpy as np
import pandas as pd
import pytest
from nbaforecast.models.rapm.design import build_design_matrix
from nbaforecast.models.rapm.fit import fit_rapm, select_alpha
from nbaforecast.models.rapm.stints import build_stints, stints_to_dataframe

LEAGUE_AVERAGE_RATE = 100.0  # baseline points per 100 possessions, before player effects
STINT_POSSESSIONS = 100  # possessions per synthetic stint — large enough that rounding to an
# integer point total introduces only negligible error relative to the true per-100 rate.


def _synthetic_stints(
    n_players: int = 12,
    n_stints: int = 4000,
    seed: int = 7,
) -> tuple[pd.DataFrame, dict[int, float], dict[int, float]]:
    """Simulate stints with known per-player true ORAPM/DRAPM and randomized lineups each stint,
    so the ridge fit has no perfect multicollinearity to hide behind. Returns ``(stints_df,
    true_orapm, true_drapm)``.
    """
    rng = np.random.default_rng(seed)
    player_ids = list(range(1, n_players + 1))
    # True effects are quite separated so recovering them is a meaningful assertion (small
    # league, thousands of stints — plenty of signal for the correctness test).
    true_orapm = {p: float(rng.uniform(-6, 6)) for p in player_ids}
    true_drapm = {p: float(rng.uniform(-6, 6)) for p in player_ids}

    rows = []
    for i in range(n_stints):
        lineup = rng.choice(player_ids, size=10, replace=False)
        off_players = lineup[:5].tolist()
        def_players = lineup[5:].tolist()
        # Points per 100 possessions for this stint = league average + sum of true offense
        # effects (for the offense five) + sum of true defense effects (for the defense five,
        # where a *positive* DRAPM means the defense concedes more, mirroring how RAPM =
        # ORAPM + DRAPM sums to overall plus-minus contribution downstream).
        true_rate = (
            LEAGUE_AVERAGE_RATE
            + sum(true_orapm[p] for p in off_players)
            + sum(true_drapm[p] for p in def_players)
        )
        points = round(true_rate / 100.0 * STINT_POSSESSIONS)
        rows.append(
            {
                "game_id": f"G{i // 200}",  # several stints per synthetic "game"
                "period": 1,
                "offense_team_id": 1,
                "defense_team_id": 2,
                "points": points,
                "possessions": STINT_POSSESSIONS,
                "off_player_ids": off_players,
                "def_player_ids": def_players,
            }
        )
    return pd.DataFrame(rows), true_orapm, true_drapm


def test_fit_rapm_recovers_true_effects_at_low_alpha() -> None:
    stints, true_orapm, true_drapm = _synthetic_stints()
    design = build_design_matrix(stints)
    fit_result = fit_rapm(design, alpha=1.0)  # small alpha: little shrinkage needed (no noise)

    ratings_by_player = {r.player_id: r for r in fit_result.ratings}
    for player_id, expected_orapm in true_orapm.items():
        assert ratings_by_player[player_id].orapm == pytest.approx(expected_orapm, abs=1.0)
    for player_id, expected_drapm in true_drapm.items():
        assert ratings_by_player[player_id].drapm == pytest.approx(expected_drapm, abs=1.0)


def test_fit_rapm_rapm_is_sum_of_orapm_and_drapm() -> None:
    stints, _, _ = _synthetic_stints(n_stints=500)
    design = build_design_matrix(stints)
    fit_result = fit_rapm(design, alpha=500.0)
    for rating in fit_result.ratings:
        assert rating.rapm == pytest.approx(rating.orapm + rating.drapm)


def test_select_alpha_picks_from_grid() -> None:
    stints, _, _ = _synthetic_stints(n_stints=800)
    grid = (10.0, 1_000.0, 100_000.0)
    alpha = select_alpha(stints, alpha_grid=grid, n_splits=2)
    assert alpha in grid


def test_select_alpha_falls_back_with_single_game() -> None:
    stints = stints_to_dataframe(
        build_stints(
            pd.DataFrame(
                [
                    {
                        "game_id": "G1",
                        "period": 1,
                        "start_seconds": 0,
                        "offense_team_id": 1,
                        "defense_team_id": 2,
                        "points": 2,
                        "off_player_ids": [1, 2, 3, 4, 5],
                        "def_player_ids": [6, 7, 8, 9, 10],
                    }
                ]
            )
        )
    )
    grid = (10.0, 100.0, 1_000.0)
    alpha = select_alpha(stints, alpha_grid=grid)
    assert alpha == grid[len(grid) // 2]
