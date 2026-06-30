"""Dependency injection — backend-api.md Prompt 2.

DB session, Redis client, and ``ModelProvider`` — every router takes these as FastAPI
``Depends(...)`` rather than reaching for global state directly, so they're trivially
overridable in tests (see ``backend/tests/api/conftest.py``).
"""

from collections.abc import AsyncIterator

import redis.asyncio as redis
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from nbaforecast.api.model_provider import ModelProvider
from nbaforecast.config.settings import get_settings
from nbaforecast.storage.database import get_session

# Quoted: redis.Redis is only a generic for static type-checking (no real __class_getitem__), so
# `redis.Redis[str]` would raise TypeError if evaluated at runtime. A string annotation is never
# evaluated; module-wide `from __future__ import annotations` was tried instead but breaks
# FastAPI's runtime dependency resolution for Request/AsyncSession/ModelProvider below, which
# needs get_type_hints() to resolve those to real, importable classes.
_redis_client: "redis.Redis[str] | None" = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a transactional ``AsyncSession`` (re-exports storage.database.get_session)."""
    async for session in get_session():
        yield session


def get_redis_client() -> "redis.Redis[str]":
    """Process-level Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client


def get_model_provider(request: Request) -> ModelProvider:
    """The app-lifetime ``ModelProvider``, set on ``app.state`` during the lifespan startup."""
    provider: ModelProvider = request.app.state.model_provider
    return provider
