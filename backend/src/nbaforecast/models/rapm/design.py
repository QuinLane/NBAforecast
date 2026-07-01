"""Sparse design matrix — rapm.md Prompt 2 / §2.

Builds the ridge regression inputs from a stint DataFrame (``stints.py`` output):

- ``X``: sparse CSR matrix, one row per stint, two columns per player (an offense column and a
  defense column — the ORAPM/DRAPM split, rapm.md §9). Offense players get ``+1`` in their offense
  column; defense players get ``+1`` in their defense column.
- ``y``: points scored per 100 possessions for that stint (the offensive team's rate).
- ``weights``: each stint's possession count (longer stints carry more signal).
- ``player_index``: maps ``player_id -> (offense_column, defense_column)`` so fitted
  coefficients can be attributed back to players.

With thousands of players across a multi-season window and possibly millions of stints, ``X`` is
~99.9% zeros; a dense array would not fit in memory, hence ``scipy.sparse.csr_matrix`` (built via
COO for cheap incremental construction, then converted to CSR for the solver).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse

POSSESSIONS_PER_RATE = 100.0


@dataclass(slots=True)
class PlayerIndex:
    """Column index of each player's offense/defense coefficient in the design matrix."""

    player_ids: list[int]
    offense_columns: dict[int, int]
    defense_columns: dict[int, int]
    n_columns: int

    def offense_column(self, player_id: int) -> int:
        return self.offense_columns[player_id]

    def defense_column(self, player_id: int) -> int:
        return self.defense_columns[player_id]


@dataclass(slots=True)
class RapmDesignMatrix:
    """The full ridge-regression input bundle for a window of stints."""

    x: sparse.csr_matrix
    y: np.ndarray
    weights: np.ndarray
    player_index: PlayerIndex
    game_ids: np.ndarray  # aligned with rows of x/y/weights — which game each stint belongs to


def _build_player_index(stints: pd.DataFrame) -> PlayerIndex:
    player_ids: set[int] = set()
    for column in ("off_player_ids", "def_player_ids"):
        for lineup in stints[column]:
            player_ids.update(int(p) for p in lineup)
    sorted_ids = sorted(player_ids)

    offense_columns = {player_id: 2 * i for i, player_id in enumerate(sorted_ids)}
    defense_columns = {player_id: 2 * i + 1 for i, player_id in enumerate(sorted_ids)}
    return PlayerIndex(
        player_ids=sorted_ids,
        offense_columns=offense_columns,
        defense_columns=defense_columns,
        n_columns=2 * len(sorted_ids),
    )


def build_design_matrix(stints: pd.DataFrame) -> RapmDesignMatrix:
    """Build the sparse ``X``, target ``y``, weights, and player index from ``stints``.

    Args:
        stints: A DataFrame shaped like ``stints.stints_to_dataframe`` output — one row per
            stint with ``off_player_ids, def_player_ids, points, possessions, game_id`` (and any
            other columns, which are ignored).

    Returns:
        A :class:`RapmDesignMatrix`. Empty input yields an empty (0-row) matrix with an empty
        player index.
    """
    if stints.empty:
        empty_index = PlayerIndex(
            player_ids=[], offense_columns={}, defense_columns={}, n_columns=0
        )
        return RapmDesignMatrix(
            x=sparse.csr_matrix((0, 0)),
            y=np.array([]),
            weights=np.array([]),
            player_index=empty_index,
            game_ids=np.array([]),
        )

    player_index = _build_player_index(stints)

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    y = np.empty(len(stints), dtype=float)
    weights = np.empty(len(stints), dtype=float)
    game_ids = np.empty(len(stints), dtype=object)

    for row_idx, record in enumerate(stints.to_dict("records")):
        possessions = int(record["possessions"])
        points = int(record["points"])
        for player_id in record["off_player_ids"]:
            rows.append(row_idx)
            cols.append(player_index.offense_column(int(player_id)))
            data.append(1.0)
        for player_id in record["def_player_ids"]:
            rows.append(row_idx)
            cols.append(player_index.defense_column(int(player_id)))
            data.append(1.0)

        weights[row_idx] = possessions
        # Points per 100 possessions; possessions is always >= 1 by construction (stints.py).
        y[row_idx] = (points / possessions) * POSSESSIONS_PER_RATE
        game_ids[row_idx] = record["game_id"]

    x = sparse.coo_matrix((data, (rows, cols)), shape=(len(stints), player_index.n_columns)).tocsr()

    return RapmDesignMatrix(x=x, y=y, weights=weights, player_index=player_index, game_ids=game_ids)
