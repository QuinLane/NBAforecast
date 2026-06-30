"""Async SQLAlchemy engine, session factory, and declarative ``Base``.

This module owns the database connectivity primitives shared by every repository and the
Alembic environment. Models live in :mod:`nbaforecast.storage.models` and inherit :class:`Base`.
"""

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from nbaforecast.config.settings import get_settings

# Deterministic constraint/index names so Alembic migrations and the schema-match test are
# stable and reviewable (PostgreSQL otherwise auto-names them unpredictably).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base carrying the shared metadata + naming convention."""

    metadata = metadata


def create_engine() -> AsyncEngine:
    """Create an async engine from the configured ``NBAF_POSTGRES_URL``."""
    settings = get_settings()
    return create_async_engine(settings.postgres_url, pool_pre_ping=True)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-level async engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-level session factory bound to the shared engine."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a transactional ``AsyncSession`` (FastAPI/Prefect dependency)."""
    async with get_sessionmaker()() as session:
        yield session
