"""Unit tests for the bronze ObjectStore using an in-memory fake S3 client (no network)."""

import json

from botocore.exceptions import ClientError
from nbaforecast.config.settings import Settings
from nbaforecast.storage.object_store import ObjectStore


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeS3:
    """Minimal in-memory stand-in for a boto3 S3 client."""

    def __init__(self, existing_buckets: set[str] | None = None) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.buckets: set[str] = set(existing_buckets or set())
        self.created: list[str] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> dict[str, str]:
        self.objects[(Bucket, Key)] = Body
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        return {"Body": _Body(self.objects[(Bucket, Key)])}

    def head_bucket(self, *, Bucket: str) -> dict[str, str]:
        if Bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")
        return {}

    def create_bucket(self, *, Bucket: str) -> dict[str, str]:
        self.buckets.add(Bucket)
        self.created.append(Bucket)
        return {}


def _settings() -> Settings:
    return Settings(postgres_url="postgresql+asyncpg://u:p@localhost/db", s3_bucket="test-bucket")


def _store(client: FakeS3) -> ObjectStore:
    return ObjectStore(settings=_settings(), client=client)


def test_raw_key_layout() -> None:
    assert (
        ObjectStore.raw_key("stats_nba", "boxscore", "2023-24", "0022300001")
        == "raw/stats_nba/boxscore/2023-24/0022300001.json"
    )


def test_put_then_get_round_trips() -> None:
    store = _store(FakeS3())
    payload = {"resultSets": [{"rowSet": [[1, 2, 3]]}]}
    key = store.put_raw("stats_nba", "pbp", "2023-24", "0022300001", payload)
    assert key == "raw/stats_nba/pbp/2023-24/0022300001.json"
    assert store.get_raw("stats_nba", "pbp", "2023-24", "0022300001") == payload


def test_put_is_idempotent_overwrite() -> None:
    client = FakeS3()
    store = _store(client)
    store.put_raw("stats_nba", "pbp", "2023-24", "g1", {"v": 1})
    store.put_raw("stats_nba", "pbp", "2023-24", "g1", {"v": 2})
    # Same key overwritten, not duplicated.
    assert len(client.objects) == 1
    assert store.get_raw("stats_nba", "pbp", "2023-24", "g1") == {"v": 2}


def test_quarantine_writes_envelope_under_quarantine_prefix() -> None:
    client = FakeS3()
    store = _store(client)
    key = store.quarantine({"bad": "data"}, "schema failed", "stats_nba", "pbp", "g1")
    assert key == "quarantine/stats_nba/pbp/g1.json"
    stored = json.loads(client.objects[("test-bucket", key)])
    assert stored["error"] == "schema failed"
    assert stored["payload"] == {"bad": "data"}
    assert "quarantined_at" in stored


def test_ensure_bucket_creates_when_missing() -> None:
    client = FakeS3(existing_buckets=set())
    _store(client).ensure_bucket()
    assert client.created == ["test-bucket"]


def test_ensure_bucket_noop_when_present() -> None:
    client = FakeS3(existing_buckets={"test-bucket"})
    _store(client).ensure_bucket()
    assert client.created == []
