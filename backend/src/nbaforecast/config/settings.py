"""Application settings loaded from environment variables (NBAF_ prefix)."""

import os
from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, sourced from NBAF_-prefixed environment variables.

    Load via ``get_settings()`` so the result is cached for the process lifetime.
    Set ``NBAF_ENV=test`` to indicate a test environment; settings are otherwise
    identical — callers that need test-specific behaviour should branch on this field.
    """

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

    # ── App ───────────────────────────────────────────────────────────────
    env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @field_validator("env")
    @classmethod
    def _validate_env(cls, v: str) -> str:
        allowed = {"development", "test", "production"}
        if v not in allowed:
            raise ValueError(f"env must be one of {allowed}, got {v!r}")
        return v

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got {v!r}")
        return upper

    def configure_mlflow_env(self) -> None:
        """Expose S3 credentials as AWS SDK env vars so MLflow's boto3 client picks them up.

        MLflow uses the standard AWS SDK environment variables for S3 artifact storage.
        Calling this once at process startup ensures the NBAF_ credentials are the
        single source of truth — no bare AWS_* vars needed in .env.
        """
        os.environ.setdefault("AWS_ACCESS_KEY_ID", self.s3_access_key.get_secret_value())
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", self.s3_secret_key.get_secret_value())
        os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", self.s3_endpoint_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-level Settings singleton (cached after first call)."""
    return Settings()
