"""Validate every silver Pandera schema against saved raw fixtures (data-pipeline.md Prompt 5).

For each entity: the parsed fixture passes validation, a deliberately corrupted copy is rejected,
and feeding the corrupted batch through ``load_silver`` quarantines it and raises.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from nbaforecast.errors import DataValidationError
from nbaforecast.ingestion.load import load_silver
from nbaforecast.ingestion.parse import (
    parse_games,
    parse_play_by_play,
    parse_player_game_stats,
    parse_possessions,
    parse_shots,
    parse_team_game_stats,
)
from nbaforecast.ingestion.schemas import validate

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HOME_TEAM = 1610612747
GAME_ID = "0022300001"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@dataclass
class Case:
    name: str
    table: str
    fixture: str
    parse: Callable[[Any], pd.DataFrame]
    corrupt: Callable[[pd.DataFrame], pd.DataFrame]


def _corrupt(column: str, value: Any) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def _apply(df: pd.DataFrame) -> pd.DataFrame:
        bad = df.copy()
        bad.loc[0, column] = value
        return bad

    return _apply


def _corrupt_home_eq_away(df: pd.DataFrame) -> pd.DataFrame:
    bad = df.copy()
    bad.loc[0, "away_team_id"] = bad.loc[0, "home_team_id"]
    return bad


CASES = [
    Case("games", "games", "schedule.json", parse_games, _corrupt_home_eq_away),
    Case(
        "team_game_stats",
        "team_game_stats",
        "boxscore.json",
        lambda raw: parse_team_game_stats(raw, HOME_TEAM),
        _corrupt("pts", -1),
    ),
    Case(
        "player_game_stats",
        "player_game_stats",
        "boxscore.json",
        lambda raw: parse_player_game_stats(raw, HOME_TEAM),
        _corrupt("usage_rate", 1.5),
    ),
    Case("play_by_play", "play_by_play", "pbp.json", parse_play_by_play, _corrupt("period", 0)),
    Case(
        "shots",
        "shots",
        "shots.json",
        lambda raw: parse_shots(raw, 2023),
        _corrupt("loc_x", 100_000),
    ),
    Case(
        "possessions",
        "possessions",
        "possessions.json",
        lambda raw: parse_possessions(raw, GAME_ID),
        _corrupt("points", 50),
    ),
]
IDS = [c.name for c in CASES]


class FakeSession:
    def __init__(self) -> None:
        self.executed: list[Any] = []

    async def execute(self, statement: Any) -> None:
        self.executed.append(statement)


class FakeStore:
    def __init__(self) -> None:
        self.quarantined: list[str] = []

    def quarantine(self, payload: Any, error: str, source: str, endpoint: str, key: str) -> str:
        self.quarantined.append(error)
        return key


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_valid_fixture_passes(case: Case) -> None:
    df = case.parse(_load(case.fixture))
    assert not df.empty
    validate(case.table, df)  # must not raise


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_corrupt_fixture_is_rejected(case: Case) -> None:
    bad = case.corrupt(case.parse(_load(case.fixture)))
    with pytest.raises(DataValidationError):
        validate(case.table, bad)


@pytest.mark.parametrize("case", CASES, ids=IDS)
async def test_corrupt_batch_is_quarantined_and_raises(case: Case) -> None:
    bad = case.corrupt(case.parse(_load(case.fixture)))
    session, store = FakeSession(), FakeStore()
    with pytest.raises(DataValidationError):
        await load_silver(
            session,  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            case.table,
            bad,
            season_start_year=2023,
            partition_key=GAME_ID,
            raw_payload=_load(case.fixture),
            source="stats_nba",
            endpoint=case.table,
            game_id=GAME_ID,
        )
    assert len(store.quarantined) == 1
    assert session.executed == []  # nothing loaded to the DB
