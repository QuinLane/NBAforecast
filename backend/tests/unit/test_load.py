"""Unit tests for the silver load step (validate → quarantine/raise → upsert + Parquet).

Uses a fake async session and a fake object store; Parquet is written to a tmp root.
"""

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from nbaforecast.errors import DataValidationError
from nbaforecast.ingestion.load import _records, load_silver


class FakeSession:
    def __init__(self) -> None:
        self.executed: list[Any] = []

    async def execute(self, statement: Any) -> None:
        self.executed.append(statement)


class FakeStore:
    def __init__(self) -> None:
        self.quarantined: list[tuple[str, str]] = []

    def quarantine(self, payload: Any, error: str, source: str, endpoint: str, key: str) -> str:
        self.quarantined.append((key, error))
        return f"quarantine/{source}/{endpoint}/{key}.json"


def _valid_games_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "0022300001",
                "season": "2023-24",
                "season_start_year": 2023,
                "season_type": "Regular Season",
                "game_date": pd.Timestamp("2023-10-24").date(),
                "game_datetime": None,
                "home_team_id": 1610612747,
                "away_team_id": 1610612738,
                "home_score": 110,
                "away_score": 105,
                "status": "final",
                "num_periods": 4,
            }
        ]
    )


def test_records_converts_nan_and_numpy_to_python() -> None:
    df = pd.DataFrame([{"a": 1, "b": None, "c": 2.5}])  # b -> NaN via float column
    records = _records(df)
    assert records[0]["a"] == 1
    assert isinstance(records[0]["a"], int)
    assert records[0]["b"] is None
    assert records[0]["c"] == 2.5


@pytest.fixture
def parquet_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    class FakeSettings:
        parquet_root = str(tmp_path)

    monkeypatch.setattr("nbaforecast.storage.parquet_io.get_settings", lambda: FakeSettings())
    return tmp_path


@pytest.mark.usefixtures("parquet_root")
async def test_load_silver_success_upserts_and_writes_parquet() -> None:
    session, store = FakeSession(), FakeStore()
    result = await load_silver(
        session,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        "games",
        _valid_games_df(),
        season_start_year=2023,
        partition_key="2023",
        raw_payload={"resultSets": []},
        source="stats_nba",
        endpoint="schedule",
    )
    assert result.rows == 1
    assert len(session.executed) == 1  # one upsert statement
    assert store.quarantined == []
    assert result.parquet_path is not None
    assert result.parquet_path.exists()


@pytest.mark.usefixtures("parquet_root")
async def test_load_silver_invalid_quarantines_and_raises() -> None:
    session, store = FakeSession(), FakeStore()
    bad = _valid_games_df()
    bad.loc[0, "away_team_id"] = bad.loc[0, "home_team_id"]  # violates home != away

    with pytest.raises(DataValidationError):
        await load_silver(
            session,  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            "games",
            bad,
            season_start_year=2023,
            partition_key="2023",
            raw_payload={"resultSets": []},
            source="stats_nba",
            endpoint="schedule",
        )
    assert len(store.quarantined) == 1  # bad payload preserved
    assert session.executed == []  # nothing written to the DB
