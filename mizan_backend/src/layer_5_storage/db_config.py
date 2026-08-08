"""Layer 5 — async SQLAlchemy engine/session configuration.

Defaults to a local SQLite database (via `aiosqlite`) so the backend
runs out of the box for development and automated tests without any
external services; point `DATABASE_URL` at PostgreSQL (via `asyncpg`)
for production. Migrations belong in `layer_5_storage/migrations/`
(Alembic) — `init_models` here is a dev/test convenience only.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings

from .base_model import Base

#: Last-resort fallback, used only if configuration cannot be loaded at
#: all. The real default lives on `config.Settings.database_url`, which
#: is what `DATABASE_URL` overrides.
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./mizan_backend.db"


def _configured_database_url() -> str:
    """The database URL from configuration, honouring `DATABASE_URL`.

    Read through `config.Settings` rather than hard-coded here: this
    module's own docstring tells operators to point `DATABASE_URL` at
    PostgreSQL for production, and until this looked the setting up,
    that instruction silently did nothing — a deployment aimed at
    Postgres would have kept writing to a local SQLite file.

    Layer 5 importing `config` is expected: `config.py` names the
    storage and data-access layers, alongside the composition root, as
    its legitimate consumers precisely because they need connection
    strings.
    """
    try:
        return get_settings().database_url
    except Exception:  # noqa: BLE001 - never let config break engine creation
        return DEFAULT_DATABASE_URL


def build_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Creates a new async engine for `database_url`.

    Exposed as a standalone function (rather than only a module-level
    singleton) so tests can build isolated, disposable engines (e.g.
    an in-memory SQLite database per test) without touching the
    process-wide `engine`.
    """
    url = database_url or _configured_database_url()
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    new_engine = create_async_engine(
        url, echo=False, future=True, connect_args=connect_args
    )

    if is_sqlite:
        # SQLite does not enforce FOREIGN KEY constraints unless a
        # connection explicitly opts in — without this, a bad
        # `wallet_id` on a ledger entry (or any other FK violation)
        # would silently succeed under the SQLite dev/test database
        # while correctly raising under Postgres in production. Every
        # new DBAPI connection this engine opens gets the pragma
        # applied immediately, so dev/test behaviour matches
        # production.
        @event.listens_for(new_engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(
            dbapi_connection: Any, connection_record: Any
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return new_engine


def build_session_factory(bind_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=bind_engine, expire_on_commit=False, class_=AsyncSession)


# Process-wide default engine/session-factory, used by the composition
# root (`main.py`) and by repository implementations unless a test
# overrides them with `build_engine`/`build_session_factory`.
engine: AsyncEngine = build_engine()
async_session_factory: async_sessionmaker[AsyncSession] = build_session_factory(engine)


async def init_models(bind_engine: Optional[AsyncEngine] = None) -> None:
    """Creates all tables known to `Base.metadata`.

    Intended for local development and automated tests; production
    deployments should apply versioned Alembic migrations instead.
    """
    target_engine = bind_engine or engine
    async with target_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope(
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
) -> AsyncIterator[AsyncSession]:
    """Context-managed session for use outside of FastAPI's dependency
    injection (e.g. inside background tasks)."""
    factory = session_factory or async_session_factory
    async with factory() as session:
        yield session


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: `session: AsyncSession = Depends(get_db_session)`."""
    async with async_session_factory() as session:
        yield session
