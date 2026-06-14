"""SQLAlchemy declarative base + engine factory."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.settings import Settings, get_settings


def _apply_sqlite_pragmas(dbapi_conn, _record) -> None:
    """Per-connection SQLite tuning.

    WAL lets readers run concurrently with a writer, and a generous
    `busy_timeout` makes a blocked writer *wait* for the lock instead of
    raising `database is locked` — important now that multiple download
    workers write concurrently.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Lazy-create the global async engine."""
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        # `pool_pre_ping` is off because aiosqlite fires pings across
        # event loops and trips `MissingGreenlet`. SQLite uses the
        # default `AsyncAdaptedQueuePool` — `NullPool` would create a
        # new connection per checkout and re-trigger the greenlet
        # issue more often.
        _engine = create_async_engine(
            settings.db_url, echo=False, future=True, pool_pre_ping=False,
        )
        event.listen(_engine.sync_engine, "connect", _apply_sqlite_pragmas)
    return _engine


def get_sessionmaker(settings: Settings | None = None) -> async_sessionmaker:
    """Lazy-create the global sessionmaker."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(settings),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    """Dispose of the engine (call on shutdown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
