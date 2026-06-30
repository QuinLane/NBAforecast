"""Leakage-safe primitives — feature-engineering.md Prompt 1.

Every helper here respects an implicit or explicit "as of" boundary: a row's feature value is
computed only from rows strictly before it in time. None of them ever read the current row's
own ``value`` or any row dated after it — see ``backend/tests/ml/test_primitives.py`` for the
regression tests that pin this down.
"""

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0


def _grouped_as_of(
    df: pd.DataFrame,
    group_keys: str | Sequence[str],
    datetime_col: str,
    fn: Callable[[pd.DataFrame], pd.Series],
) -> pd.Series:
    """Sort each ``group_keys`` group by ``datetime_col``, apply ``fn``, realign to ``df.index``.

    Iterates groups manually and concatenates rather than ``DataFrameGroupBy.apply`` — the
    latter collapses a Series-shaped per-group result into a single-row DataFrame when there's
    only one group, which silently breaks index alignment.
    """
    keys = [group_keys] if isinstance(group_keys, str) else list(group_keys)
    parts = [
        fn(group.sort_values(datetime_col, kind="mergesort"))
        for _, group in df.groupby(keys, sort=False)
    ]
    result = pd.concat(parts) if parts else pd.Series(dtype="float64")
    return result.reindex(df.index)


def rolling_as_of(
    df: pd.DataFrame,
    group_keys: str | Sequence[str],
    value: str,
    window: int,
    datetime_col: str,
    *,
    min_periods: int = 1,
    agg: str = "mean",
) -> pd.Series:
    """Rolling ``agg`` of ``value`` over the trailing ``window`` rows per group, as of each row.

    Time-ordered within each group, then ``shift(1)`` before rolling so the current row is
    excluded from its own aggregate — e.g. a team's "rolling net rating over its last 10 games"
    for tonight's game never includes tonight's own result.
    """

    def _fn(g: pd.DataFrame) -> pd.Series:
        return g[value].shift(1).rolling(window, min_periods=min_periods).agg(agg)

    return _grouped_as_of(df, group_keys, datetime_col, _fn)


def as_of_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: str | Sequence[str],
    datetime_col: str,
    *,
    allow_exact_matches: bool = False,
    suffixes: tuple[str, str] = ("", "_asof"),
) -> pd.DataFrame:
    """Point-in-time join: attach the most recent ``right`` row per ``on`` group as of each
    ``left`` row's ``datetime_col``.

    Wraps :func:`pandas.merge_asof` with ``direction="backward"``. ``allow_exact_matches``
    defaults to ``False`` (strictly *before*, never equal) to enforce the cardinal no-leakage
    rule by default; only pass ``True`` when the matched ``right`` row genuinely represents
    information available before tip-off despite sharing a timestamp.
    """
    by = [on] if isinstance(on, str) else list(on)
    return pd.merge_asof(
        left.sort_values(datetime_col, kind="mergesort"),
        right.sort_values(datetime_col, kind="mergesort"),
        on=datetime_col,
        by=by,
        direction="backward",
        allow_exact_matches=allow_exact_matches,
        suffixes=suffixes,
    )


def days_rest(df: pd.DataFrame, group_keys: str | Sequence[str], datetime_col: str) -> pd.Series:
    """Days since each group's previous row (``NaN`` for a group's first row).

    ``datetime_col`` must be a ``datetime64`` dtype (a game's own date is known ahead of tip-off;
    only the *previous* game's date is the leakage-sensitive part, and that is always strictly
    earlier by construction).
    """

    def _fn(g: pd.DataFrame) -> pd.Series:
        result: pd.Series = g[datetime_col].diff().dt.days
        return result

    return _grouped_as_of(df, group_keys, datetime_col, _fn)


def schedule_density(
    df: pd.DataFrame,
    group_keys: str | Sequence[str],
    datetime_col: str,
    window_days: int,
) -> pd.Series:
    """Count of a group's prior games strictly within the trailing ``window_days`` days.

    Excludes the current row itself. Used for fatigue features like ``games_last_7d`` /
    ``games_last_14d``.
    """

    def _fn(g: pd.DataFrame) -> pd.Series:
        values = g[datetime_col].to_numpy()
        window = np.timedelta64(window_days, "D")
        # searchsorted(..., side="right") counts values <= (values[i] - window); subtracting
        # that from the row's own position (i, 0-indexed = count of strictly-prior rows) leaves
        # exactly the prior rows whose date is in (values[i] - window, values[i]).
        left_idx = np.searchsorted(values, values - window, side="right")
        counts = np.arange(len(values)) - left_idx
        return pd.Series(counts, index=g.index)

    return _grouped_as_of(df, group_keys, datetime_col, _fn)


def _haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    lat1_r, lon1_r, lat2_r, lon2_r = (np.radians(s) for s in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    result: pd.Series = EARTH_RADIUS_KM * c
    return result


def travel_distance(
    df: pd.DataFrame,
    group_keys: str | Sequence[str],
    lat_col: str,
    lon_col: str,
    datetime_col: str,
) -> pd.Series:
    """Great-circle distance (km) from a group's previous row's location to its current one.

    ``lat_col``/``lon_col`` hold *where the game at that row was played* (the caller resolves
    this to the home team's arena, or the opponent's for a road game — see
    ``features/team_game.py``). ``NaN`` for a group's first row (no previous location).
    """

    def _fn(g: pd.DataFrame) -> pd.Series:
        prev_lat = g[lat_col].shift(1)
        prev_lon = g[lon_col].shift(1)
        return _haversine_km(prev_lat, prev_lon, g[lat_col], g[lon_col])

    return _grouped_as_of(df, group_keys, datetime_col, _fn)
