"""Unit tests for ingestion orchestration (clients/parse/load monkeypatched — no IO)."""

from datetime import date
from typing import Any

import nbaforecast.ingestion.pipeline as pl
import pandas as pd
import pytest
from nbaforecast.ingestion.pipeline import GameMeta, ingest_game, ingest_schedule, season_for_date


class FakeStore:
    def __init__(self) -> None:
        self.puts: list[tuple[str, str, str]] = []

    def put_raw(self, source: str, endpoint: str, season: str, key: str, payload: Any) -> str:
        self.puts.append((source, endpoint, key))
        return key


@pytest.fixture
def load_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_load(
        session: Any, store: Any, table: str, df: pd.DataFrame, **kwargs: Any
    ) -> None:
        calls.append({"table": table, **kwargs})

    monkeypatch.setattr(pl, "load_silver", fake_load)
    return calls


def test_season_for_date() -> None:
    assert season_for_date(date(2023, 11, 1)) == "2023-24"
    assert season_for_date(date(2024, 3, 1)) == "2023-24"
    assert season_for_date(date(2024, 10, 30)) == "2024-25"


async def test_ingest_game_loads_every_entity(
    monkeypatch: pytest.MonkeyPatch, load_calls: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(pl, "fetch_boxscore", lambda gid: {"box": 1})
    monkeypatch.setattr(pl, "fetch_pbp", lambda gid: {"pbp": 1})
    monkeypatch.setattr(pl, "fetch_shots", lambda gid, season=None, season_type=None: {"shots": 1})
    monkeypatch.setattr(pl, "fetch_possessions", lambda gid: [{"p": 1}])

    async def fake_ensure_players(session, box_raw):
        return 0

    monkeypatch.setattr(pl, "ensure_players_from_boxscore", fake_ensure_players)
    df = pd.DataFrame([{"x": 1}])
    monkeypatch.setattr(pl, "parse_team_game_stats", lambda raw, home: df)
    monkeypatch.setattr(pl, "parse_player_game_stats", lambda raw, home: df)
    monkeypatch.setattr(pl, "parse_play_by_play", lambda raw: df)
    monkeypatch.setattr(pl, "parse_shots", lambda raw, year: df)
    monkeypatch.setattr(pl, "parse_possessions", lambda raw, gid: df)

    store = FakeStore()
    meta = GameMeta("0022300001", "2023-24", 2023, 123)
    done = await ingest_game(None, store, meta)  # type: ignore[arg-type]

    assert done == {"boxscore", "pbp", "shots", "possessions"}
    assert [c["table"] for c in load_calls] == [
        "team_game_stats",
        "player_game_stats",
        "play_by_play",
        "shots",
        "possessions",
    ]
    assert load_calls[-1]["game_id"] == "0022300001"  # possessions replace-by-game
    # box, pbp, shots, possessions → 4 bronze writes
    assert len(store.puts) == 4


async def test_ingest_schedule_returns_metas(
    monkeypatch: pytest.MonkeyPatch, load_calls: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(
        pl, "fetch_schedule", lambda season, stype, date_from=None, date_to=None: {"s": 1}
    )
    monkeypatch.setattr(
        pl,
        "parse_games",
        lambda raw: pd.DataFrame(
            [
                {"game_id": "g1", "home_team_id": 10, "season_type": "Regular Season"},
                {"game_id": "g2", "home_team_id": 20, "season_type": "Playoffs"},
            ]
        ),
    )
    store = FakeStore()
    metas = await ingest_schedule(None, store, "2023-24")  # type: ignore[arg-type]

    assert [m.game_id for m in metas] == ["g1", "g2"]
    assert metas[0].season_start_year == 2023
    assert metas[1].home_team_id == 20
    assert load_calls[0]["table"] == "games"
