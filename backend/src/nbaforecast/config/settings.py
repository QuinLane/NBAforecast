"""Application settings loaded from environment variables (NBAF_ prefix)."""

import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, sourced from NBAF_-prefixed environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="NBAF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Postgres ──────────────────────────────────────────────────────────
    # Full async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host/db
    postgres_url: str

    # ── Redis ─────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── MinIO / S3 ────────────────────────────────────────────────────────
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: SecretStr = SecretStr("minioadmin")
    s3_secret_key: SecretStr = SecretStr("minioadmin")
    s3_bucket: str = "nbaforecast"

    # ── MLflow ────────────────────────────────────────────────────────────
    mlflow_tracking_uri: str = "http://localhost:5000"

    # ── Ingestion (nba_api / pbpstats) ────────────────────────────────────
    # stats.nba.com is finicky: throttle calls, retry with backoff, send real headers.
    ingest_throttle_seconds: float = 0.6
    ingest_request_timeout: int = 60
    ingest_max_retries: int = 5
    ingest_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    # Local cache directory pbpstats writes raw responses into.
    pbpstats_cache_dir: str = "data/pbpstats_cache"
    # Root of the silver Parquet analytical store (partitioned by season_start_year).
    parquet_root: str = "data/silver"

    # ── App ───────────────────────────────────────────────────────────────
    env: Literal["development", "test", "production"] = "development"
    log_level: Annotated[
        Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        BeforeValidator(str.upper),
    ] = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    def configure_mlflow_env(self) -> None:
        """Expose S3 credentials as AWS SDK env vars so MLflow's boto3 client picks them up."""
        os.environ.setdefault("AWS_ACCESS_KEY_ID", self.s3_access_key.get_secret_value())
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", self.s3_secret_key.get_secret_value())
        os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", self.s3_endpoint_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-level Settings singleton (cached after first call)."""
    return Settings()
