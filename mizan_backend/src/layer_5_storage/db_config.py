"""Layer 5 — async SQLAlchemy engine/session configuration.

Defaults to a local SQLite database (via `aiosqlite`) so the backend
runs out of the box for development and automated tests without any
external services; point `DATABASE_URL` at PostgreSQL (via `asyncpg`)
for production. Migrations belong in `layer_5_storage/migrations/`
(Alembic) — `init_models` here is a dev/test convenience only.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .base_model import Base

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./mizan_backend.db"


def build_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Creates a new async engine for `database_url`.

    Exposed as a standalone function (rather than only a module-level
    singleton) so tests can build isolated, disposable engines (e.g.
    an in-memory SQLite database per test) without touching the
    process-wide `engine`.
    """
    url = database_url or DEFAULT_DATABASE_URL
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_async_engine(url, echo=False, future=True, connect_args=connect_args)


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
