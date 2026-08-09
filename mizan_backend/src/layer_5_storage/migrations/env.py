"""Alembic environment for `mizan_backend`.

Two things here are deliberate and worth knowing before editing:

**The URL comes from application configuration, not `alembic.ini`.**
`config.Settings.database_url` (i.e. the `DATABASE_URL` environment
variable) is the single source of truth, so `alembic upgrade head` and
the running application cannot be aimed at different databases by
someone updating one and forgetting the other.

**Batch mode is on.** SQLite cannot `ALTER TABLE ... ALTER COLUMN` or
drop a column in place; Alembic's batch mode emulates those by
recreating the table and copying the rows. Development runs on SQLite
and production on PostgreSQL, so without this a migration would pass in
CI and fail on a developer's machine — or worse, the reverse.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from config import get_settings

# Importing the models is what populates `Base.metadata`, which
# `--autogenerate` diffs the database against. A model whose module is
# never imported here is invisible to autogenerate, so this import must
# stay exhaustive — `tests/layer_5_storage_tests/test_migrations.py`
# fails if the two ever drift apart.
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.models import message_model  # noqa: F401
from src.layer_5_storage.models import queue_model  # noqa: F401
from src.layer_5_storage.models import transaction_ledger_model  # noqa: F401
from src.layer_5_storage.models import user_model  # noqa: F401
from src.layer_5_storage.models import wallet_model  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """The URL to migrate, from application configuration.

    An explicit `-x url=...` wins, which is what the migration tests use
    to run against a disposable database without touching the
    developer's own.
    """
    overrides = context.get_x_argument(as_dictionary=True)
    if "url" in overrides:
        return overrides["url"]
    return get_settings().database_url


def _configure(connection: Connection) -> None:
    """Shared configuration for both offline and online runs."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # See the module docstring: required for SQLite to survive any
        # migration that alters or drops a column.
        render_as_batch=True,
        # Without this, a column whose type changes is silently ignored
        # by autogenerate, and the drift is only discovered in
        # production.
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic … --sql`).

    Useful when a DBA must review and apply the statements by hand,
    which is the normal path for a regulated production database.
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Runs migrations through an async engine.

    The application's drivers are async (`aiosqlite`, `asyncpg`), so
    Alembic has to drive them from an async engine and hand the
    migration a sync-style connection via `run_sync`.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Applies migrations against a live database."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
