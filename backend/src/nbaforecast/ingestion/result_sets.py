"""Helpers for reading nba_api ``resultSets`` payloads.

``nba_api`` endpoints return ``{"resultSets": [{"name", "headers", "rowSet"}, ...]}``. These
helpers turn a named result set into a list of dicts / a DataFrame without any value mapping.
"""

from typing import Any

import pandas as pd

from nbaforecast.errors import IngestionError

JsonDict = dict[str, Any]


def result_set(raw: JsonDict, name: str) -> JsonDict:
    """Return the named result set object from an nba_api payload.

    Raises:
        IngestionError: if no result set with ``name`` is present.
    """
    for rs in raw.get("resultSets", []):
        if rs.get("name") == name:
            return rs  # type: ignore[no-any-return]
    available = [rs.get("name") for rs in raw.get("resultSets", [])]
    raise IngestionError(f"result set {name!r} not found; available: {available}")


def result_set_records(raw: JsonDict, name: str) -> list[dict[str, Any]]:
    """Return the named result set as a list of ``{header: value}`` dicts."""
    rs = result_set(raw, name)
    headers: list[str] = rs["headers"]
    return [dict(zip(headers, row, strict=True)) for row in rs["rowSet"]]


def result_set_df(raw: JsonDict, name: str) -> pd.DataFrame:
    """Return the named result set as a DataFrame with the original NBA column names."""
    rs = result_set(raw, name)
    return pd.DataFrame(rs["rowSet"], columns=rs["headers"])
