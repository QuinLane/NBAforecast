"""Unit tests for the ingestion checkpoint logic (fake session — no DB)."""

from typing import Any

from nbaforecast.ingestion.checkpoint import REQUIRED_ENTITIES, get_checkpoint, is_complete


class FakeIngestedGame:
    def __init__(self, entities: list[str]) -> None:
        self.entities_done = {"entities": entities}


class FakeSession:
    def __init__(self, row: FakeIngestedGame | None) -> None:
        self._row = row

    async def get(self, model: Any, key: str) -> FakeIngestedGame | None:
        return self._row


async def test_get_checkpoint_empty_when_absent() -> None:
    assert await get_checkpoint(FakeSession(None), "g1") == set()  # type: ignore[arg-type]


async def test_get_checkpoint_returns_entities() -> None:
    session = FakeSession(FakeIngestedGame(["boxscore", "pbp"]))
    assert await get_checkpoint(session, "g1") == {"boxscore", "pbp"}  # type: ignore[arg-type]


async def test_is_complete_true_when_all_required_present() -> None:
    session = FakeSession(FakeIngestedGame(sorted(REQUIRED_ENTITIES)))
    assert await is_complete(session, "g1")  # type: ignore[arg-type]


async def test_is_complete_false_when_partial() -> None:
    session = FakeSession(FakeIngestedGame(["boxscore", "pbp"]))
    assert not await is_complete(session, "g1")  # type: ignore[arg-type]


def test_required_entities() -> None:
    assert {"boxscore", "pbp", "shots", "possessions"} == REQUIRED_ENTITIES
