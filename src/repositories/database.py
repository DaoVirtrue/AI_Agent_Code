"""
Async SQLAlchemy 2.0 engine and session factory.

Provides the core database infrastructure:
- AsyncEngine creation from settings
- AsyncSession factory bound to the engine
- FastAPI dependency ``get_db()`` for request-scoped sessions
- ``init_db()`` to create all tables on startup
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.infrastructure.config import Settings, get_settings


# ---------------------------------------------------------------------------
# Globals (lazy-initialized)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async SQLAlchemy engine from settings."""
    return create_async_engine(
        settings.database.url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        echo=settings.database.echo,
        pool_pre_ping=settings.database.pool_pre_ping,
        pool_recycle=settings.database.pool_recycle,
    )


def get_engine() -> AsyncEngine:
    """Return the current engine.  Call ``init_database()`` first."""
    if _engine is None:
        raise RuntimeError("Database engine not initialised. Call init_database() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current session factory."""
    if _session_factory is None:
        raise RuntimeError("Session factory not initialised. Call init_database() first.")
    return _session_factory


async def init_database(settings: Settings | None = None) -> None:
    """
    Initialise the database engine and session factory.

    Must be called during application startup before any DB access.
    """
    global _engine, _session_factory

    if settings is None:
        settings = get_settings()

    _engine = create_engine(settings)
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def close_database() -> None:
    """Gracefully dispose of the engine (call on application shutdown)."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request.

    Usage::

        from fastapi import Depends
        from src.repositories.database import get_db

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Table creation (dev / testing convenience)
# ---------------------------------------------------------------------------


async def init_db(settings: Settings | None = None) -> None:
    """Create all tables defined by models that inherit from Base.

    Safe to call multiple times – uses ``create_all`` with ``checkfirst=True``.
    """
    from .models.base import Base  # local import to avoid circular imports

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
