"""Tests for Layer 5's engine configuration.

Specifically that `DATABASE_URL` is actually honoured. This module's
docstring has always told operators to point `DATABASE_URL` at
PostgreSQL for production, but the URL was hard-coded here and the
setting was never read — so a deployment aimed at Postgres would have
kept writing to a local SQLite file, silently and with no error to
notice. A silent-failure bug of that shape deserves a test.
"""
from __future__ import annotations

import pytest

from config import get_settings
from src.layer_5_storage import db_config


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """`get_settings` is `lru_cache`d, so each test must start from a
    clean read of the environment and leave one behind."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_build_engine_uses_the_configured_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////tmp/configured-test.db")

    engine = db_config.build_engine()

    assert "configured-test.db" in str(engine.url)


def test_an_explicit_url_still_wins(monkeypatch) -> None:
    # Tests build isolated in-memory engines this way; configuration
    # must never override an explicitly requested URL.
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////tmp/configured-test.db")

    engine = db_config.build_engine("sqlite+aiosqlite:///:memory:")

    assert ":memory:" in str(engine.url)


def test_falls_back_to_the_default_when_nothing_is_configured(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    engine = db_config.build_engine()

    assert "mizan_backend.db" in str(engine.url)
