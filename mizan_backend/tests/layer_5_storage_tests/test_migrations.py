"""Tests for the Alembic migration chain.

The load-bearing one is `test_migrations_match_the_models`: it asserts
that a database built purely by running the migrations is
indistinguishable from one built from the ORM models. Without it, the
two drift the moment someone adds a column to a model and forgets the
migration — and the failure surfaces in production as a query against a
column that does not exist, which is precisely the situation these
migrations were written to clean up.

Every test runs against a disposable SQLite file (not `:memory:`, which
would vanish between the separate connections Alembic opens).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, List

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from src.layer_5_storage.base_model import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001_initial_schema"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Path]:
    """A disposable database file."""
    path = tmp_path / "migrations_test.db"
    yield path
    if path.exists():
        path.unlink()


def _alembic_config(database: Path) -> Config:
    """An Alembic config aimed at `database`.

    Passed via `-x url=` rather than by mutating the shared ini, so a
    test can never point the migration runner at a developer's own
    database.
    """
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location", str(PROJECT_ROOT / "src/layer_5_storage/migrations")
    )
    config.cmd_opts = type("Options", (), {"x": [f"url=sqlite+aiosqlite:///{database}"]})()
    return config


def _columns(database: Path, table: str) -> List[str]:
    connection = sqlite3.connect(database)
    try:
        return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
    finally:
        connection.close()


#: Tables introduced by a migration *after* the baseline. A database
#: already deployed at `BASELINE_REVISION` does not have them, so
#: `_create_legacy_schema` must not create them either — otherwise the
#: migration that adds them fails with "table already exists" against a
#: database that, in reality, would not have had it.
#:
#: Kept as an explicit list rather than derived, so adding a table is a
#: deliberate edit here; `test_the_post_baseline_table_list_is_current`
#: fails loudly if someone forgets.
POST_BASELINE_TABLES = frozenset(
    {"clinics", "queue_reservations", "properties"}
)

#: The tables migration `0001` creates — everything a database stamped
#: at the baseline is expected to already have.
BASELINE_TABLES = frozenset(
    {
        "users",
        "wallets",
        "transaction_ledger",
        "chat_threads",
        "chat_participants",
        "chat_messages",
    }
)


def _create_legacy_schema(database: Path) -> None:
    """Builds a database in the pre-RBAC shape: the baseline's tables,
    *without* the two columns migration 0002 adds and without any table
    a later migration introduces.

    This is what an already-deployed database looks like, and the
    reason the chain starts with a baseline it can be stamped at.
    """
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(
        engine,
        tables=[
            table
            for name, table in Base.metadata.tables.items()
            if name not in POST_BASELINE_TABLES
        ],
    )

    with engine.begin() as connection:
        # SQLite can drop a column since 3.35, which is enough to
        # manufacture the old shape.
        connection.execute(text("DROP INDEX IF EXISTS ix_users_role"))
        connection.execute(text("ALTER TABLE users DROP COLUMN role"))
        connection.execute(
            text("ALTER TABLE transaction_ledger DROP COLUMN direction")
        )
    engine.dispose()


class TestFreshDatabase:
    def test_upgrade_head_builds_the_whole_schema(self, database: Path) -> None:
        command.upgrade(_alembic_config(database), "head")

        tables = set(
            row[0]
            for row in sqlite3.connect(database).execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        )
        assert BASELINE_TABLES | POST_BASELINE_TABLES <= tables

    def test_the_rbac_columns_are_present(self, database: Path) -> None:
        command.upgrade(_alembic_config(database), "head")

        assert "role" in _columns(database, "users")
        assert "direction" in _columns(database, "transaction_ledger")

    def test_migrations_match_the_models(self, database: Path) -> None:
        """A migrated database and the ORM models must describe the
        same schema.

        This is the test that stops the two drifting: add a column to a
        model without writing a migration and it fails here, in CI,
        rather than in production against a column that does not exist.
        """
        command.upgrade(_alembic_config(database), "head")

        engine = create_engine(f"sqlite:///{database}")
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection,
                    opts={"compare_type": True, "render_as_batch": True},
                )
                differences = compare_metadata(context, Base.metadata)
        finally:
            engine.dispose()

        assert differences == [], (
            "the migrations and the models disagree; "
            "run 'alembic revision --autogenerate' and review the result"
        )


class TestExistingDatabase:
    """The path a deployed database takes: stamp the baseline it is
    already at, then upgrade."""

    def test_the_post_baseline_table_list_is_current(self) -> None:
        """`POST_BASELINE_TABLES` has to name every table added after
        the baseline.

        Miss one and `_create_legacy_schema` pre-creates it, so the
        migration that adds it fails against a simulated deployed
        database — a confusing "table already exists" that says nothing
        about the real cause. This fails first, and says what to do.
        """
        assert set(Base.metadata.tables) == BASELINE_TABLES | POST_BASELINE_TABLES, (
            "a table was added or removed: update BASELINE_TABLES / "
            "POST_BASELINE_TABLES so the deployed-database tests keep "
            "simulating a real upgrade path"
        )

    def test_a_new_table_is_created_on_an_existing_database(
        self, database: Path
    ) -> None:
        # The upgrade path for `0003`: a database that predates clinic
        # queues gains both tables without touching what was there.
        _create_legacy_schema(database)

        config = _alembic_config(database)
        command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")

        tables = {
            row[0]
            for row in sqlite3.connect(database).execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert POST_BASELINE_TABLES <= tables

    def test_stamping_the_baseline_then_upgrading_adds_the_columns(
        self, database: Path
    ) -> None:
        _create_legacy_schema(database)
        assert "role" not in _columns(database, "users")

        config = _alembic_config(database)
        command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")

        assert "role" in _columns(database, "users")
        assert "direction" in _columns(database, "transaction_ledger")

    def test_existing_rows_survive_and_get_the_default_role(
        self, database: Path
    ) -> None:
        # `users.role` is NOT NULL, so every account that predates roles
        # needs a value; an ordinary user is the safe reading.
        _create_legacy_schema(database)
        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO users (id, email, hashed_password, full_name, "
            "is_active, created_at, updated_at) VALUES "
            "('u1', 'legacy@example.com', 'hash', 'Legacy', 1, "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
        connection.commit()
        connection.close()

        config = _alembic_config(database)
        command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")

        connection = sqlite3.connect(database)
        try:
            rows = connection.execute("SELECT email, role FROM users").fetchall()
        finally:
            connection.close()

        assert rows == [("legacy@example.com", "user")]

    def test_historical_ledger_entries_are_left_unverifiable_not_guessed(
        self, database: Path
    ) -> None:
        """The migration must not invent a direction for old entries.

        The ledger is append-only and a transfer's two legs were written
        with the same type and the same positive amount, so their
        direction is genuinely unrecoverable. The audit service reports
        such entries as unverifiable; a migration that guessed would put
        a fabricated number in an audit report.
        """
        _create_legacy_schema(database)
        connection = sqlite3.connect(database)
        connection.executescript(
            """
            INSERT INTO users (id, email, hashed_password, full_name, is_active,
                               created_at, updated_at)
            VALUES ('u1', 'legacy@example.com', 'h', 'Legacy', 1,
                    '2026-01-01 00:00:00', '2026-01-01 00:00:00');
            INSERT INTO wallets (id, user_id, currency, balance, is_locked, version,
                                 created_at, updated_at)
            VALUES ('w1', 'u1', 'DZD', 100, 0, 1,
                    '2026-01-01 00:00:00', '2026-01-01 00:00:00');
            INSERT INTO transaction_ledger (id, wallet_id, amount, transaction_type,
                                            created_at, updated_at)
            VALUES ('e1', 'w1', 100, 'DEPOSIT',
                    '2026-01-01 00:00:00', '2026-01-01 00:00:00');
            """
        )
        connection.commit()
        connection.close()

        config = _alembic_config(database)
        command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")

        connection = sqlite3.connect(database)
        try:
            direction = connection.execute(
                "SELECT direction FROM transaction_ledger WHERE id = 'e1'"
            ).fetchone()[0]
        finally:
            connection.close()

        assert direction is None


class TestReversibility:
    def test_downgrade_removes_the_columns_and_keeps_the_data(
        self, database: Path
    ) -> None:
        # A migration you cannot reverse is one you cannot safely
        # deploy.
        config = _alembic_config(database)
        command.upgrade(config, "head")

        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO users (id, email, hashed_password, full_name, "
            "is_active, role, created_at, updated_at) VALUES "
            "('u1', 'a@example.com', 'h', 'A', 1, 'auditor', "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
        connection.commit()
        connection.close()

        # An explicit target, not a relative "-1": the latter means
        # "undo whatever happens to be head", so it silently retargets
        # every time a migration is added and stops testing what this
        # test is named after.
        command.downgrade(config, BASELINE_REVISION)

        assert "role" not in _columns(database, "users")
        assert "direction" not in _columns(database, "transaction_ledger")
        connection = sqlite3.connect(database)
        try:
            assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        finally:
            connection.close()

    def test_downgrading_clinic_queues_drops_only_its_own_tables(
        self, database: Path
    ) -> None:
        config = _alembic_config(database)
        command.upgrade(config, "head")

        command.downgrade(config, "0002_rbac_role_and_ledger_direction")

        tables = {
            row[0]
            for row in sqlite3.connect(database).execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert not (POST_BASELINE_TABLES & tables)
        assert BASELINE_TABLES <= tables
        # And the RBAC column the earlier migration added is untouched.
        assert "role" in _columns(database, "users")

    def test_a_full_round_trip_returns_to_the_same_schema(
        self, database: Path
    ) -> None:
        config = _alembic_config(database)
        command.upgrade(config, "head")
        before = _columns(database, "users")

        command.downgrade(config, "base")
        command.upgrade(config, "head")

        assert _columns(database, "users") == before


class TestChainIntegrity:
    def test_there_is_exactly_one_head(self) -> None:
        # Two heads mean two people branched the chain and neither
        # noticed; `upgrade head` then fails with an ambiguity error.
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(_alembic_config(Path("unused.db")))

        assert len(script.get_heads()) == 1

    def test_every_revision_declares_a_downgrade(self) -> None:
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(_alembic_config(Path("unused.db")))

        for revision in script.walk_revisions():
            source = Path(revision.path).read_text()
            body = source.split("def downgrade()", 1)[1]
            assert body.strip() != "-> None:\n    pass", (
                f"{revision.revision} has an empty downgrade()"
            )
