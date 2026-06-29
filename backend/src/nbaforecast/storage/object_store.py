"""Bronze object store — immutable raw landing on S3/MinIO (data-pipeline.md §2, Prompt 2).

Raw API responses are written exactly as received under ``raw/{source}/{endpoint}/{season}/``
so the pipeline can re-process without re-pulling. Writes overwrite the same key (idempotent).
Corrupted payloads are diverted to ``quarantine/`` with their error instead of being loaded.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from nbaforecast.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

Json = dict[str, Any] | list[Any]


class S3Client(Protocol):
    """Minimal S3 surface the store needs (satisfied by a boto3 S3 client)."""

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> Any: ...

    def get_object(self, *, Bucket: str, Key: str) -> Any: ...

    def head_bucket(self, *, Bucket: str) -> Any: ...

    def create_bucket(self, *, Bucket: str) -> Any: ...


def _build_client(settings: Settings) -> S3Client:
    """Construct a boto3 S3 client pointed at the configured endpoint (MinIO locally)."""
    import boto3

    client: S3Client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name="us-east-1",
    )
    return client


class ObjectStore:
    """Read/write raw JSON payloads to the bronze bucket.

    Args:
        settings: Configuration (defaults to the process settings singleton).
        client: An S3 client to use instead of constructing one (for tests / DI).
    """

    def __init__(self, settings: Settings | None = None, client: S3Client | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._bucket = self._settings.s3_bucket

    @property
    def client(self) -> S3Client:
        """The S3 client, lazily constructed on first use."""
        if self._client is None:
            self._client = _build_client(self._settings)
        return self._client

    @staticmethod
    def raw_key(source: str, endpoint: str, season: str, key: str) -> str:
        """Object key for a raw payload: ``raw/{source}/{endpoint}/{season}/{key}.json``."""
        return f"raw/{source}/{endpoint}/{season}/{key}.json"

    @staticmethod
    def quarantine_key(source: str, endpoint: str, key: str) -> str:
        """Object key for a quarantined payload under ``quarantine/``."""
        return f"quarantine/{source}/{endpoint}/{key}.json"

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist (idempotent bootstrap)."""
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self._bucket)
        except ClientError:
            logger.info("creating bucket %s", self._bucket)
            self.client.create_bucket(Bucket=self._bucket)

    def put_raw(self, source: str, endpoint: str, season: str, key: str, payload: Json) -> str:
        """Write ``payload`` as JSON to the raw prefix and return its object key.

        Overwrites any existing object at the same key, so re-pulling a game/date is safe.
        """
        object_key = self.raw_key(source, endpoint, season, key)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.client.put_object(
            Bucket=self._bucket, Key=object_key, Body=body, ContentType="application/json"
        )
        logger.debug("put_raw %s (%d bytes)", object_key, len(body))
        return object_key

    def get_raw(self, source: str, endpoint: str, season: str, key: str) -> Json:
        """Read and parse a raw JSON payload previously written with :meth:`put_raw`."""
        object_key = self.raw_key(source, endpoint, season, key)
        response = self.client.get_object(Bucket=self._bucket, Key=object_key)
        body: bytes = response["Body"].read()
        parsed: Json = json.loads(body)
        return parsed

    def quarantine(self, payload: Json, error: str, source: str, endpoint: str, key: str) -> str:
        """Write a bad payload + its error to ``quarantine/`` and return the object key.

        Used by the silver load step when validation fails, so the offending data is preserved
        for inspection instead of being dropped or loaded.
        """
        object_key = self.quarantine_key(source, endpoint, key)
        envelope = {
            "error": error,
            "quarantined_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.client.put_object(
            Bucket=self._bucket, Key=object_key, Body=body, ContentType="application/json"
        )
        logger.warning("quarantined %s: %s", object_key, error)
        return object_key
