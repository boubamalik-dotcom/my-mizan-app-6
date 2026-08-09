"""Functional tests for `UserRepository` (Layer 4): mapping between
ORM rows and plain-data records, and the unique-email guarantee."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.layer_3_business.auth.auth_exceptions import UserAlreadyExistsError
from src.layer_4_data_access.repositories.user_repository import (
    UserNotFoundError,
    UserRecord,
    UserRepository,
)
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.user_model import DEFAULT_USER_ROLE


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield build_session_factory(engine)

    await engine.dispose()


@pytest_asyncio.fixture
async def repository(session_factory: async_sessionmaker) -> UserRepository:
    return UserRepository(session_factory())


async def test_create_user_returns_an_active_user_record(
    repository: UserRepository,
) -> None:
    record = await repository.create_user(
        email="alice@example.com",
        hashed_password="$2b$12$fakehashfortests",
        full_name="Alice Example",
    )

    assert isinstance(record, UserRecord)
    assert record.id
    assert record.email == "alice@example.com"
    assert record.hashed_password == "$2b$12$fakehashfortests"
    assert record.full_name == "Alice Example"
    assert record.is_active is True
    assert record.created_at is not None


async def test_get_user_by_email_round_trips(repository: UserRepository) -> None:
    created = await repository.create_user(
        email="alice@example.com", hashed_password="hash", full_name="Alice"
    )

    fetched = await repository.get_user_by_email("alice@example.com")
    assert fetched is not None
    # Compared field-by-field rather than via dataclass equality:
    # SQLite (unlike Postgres) does not reliably round-trip `tzinfo`
    # through its `DateTime` column, so a freshly-created in-memory
    # `created_at` and the same value re-fetched from the database can
    # differ in awareness (but not in the actual point in time) —
    # immaterial here, and not something worth asserting on.
    assert fetched.id == created.id
    assert fetched.email == created.email
    assert fetched.hashed_password == created.hashed_password
    assert fetched.full_name == created.full_name
    assert fetched.is_active == created.is_active


async def test_get_user_by_email_returns_none_when_missing(
    repository: UserRepository,
) -> None:
    assert await repository.get_user_by_email("nobody@example.com") is None


async def test_get_user_by_email_is_case_sensitive_by_default(
    repository: UserRepository,
) -> None:
    # Documents current behavior: email matching is exact/case-sensitive
    # at this layer. Normalizing case is a Layer 2/3 concern if needed.
    await repository.create_user(
        email="alice@example.com", hashed_password="hash", full_name="Alice"
    )
    assert await repository.get_user_by_email("Alice@example.com") is None


async def test_create_user_rejects_a_duplicate_email(
    repository: UserRepository,
) -> None:
    await repository.create_user(
        email="alice@example.com", hashed_password="hash-one", full_name="Alice"
    )

    with pytest.raises(UserAlreadyExistsError) as exc_info:
        await repository.create_user(
            email="alice@example.com", hashed_password="hash-two", full_name="Alice 2"
        )
    assert exc_info.value.email == "alice@example.com"


async def test_a_new_account_defaults_to_the_ordinary_role(
    repository: UserRepository,
) -> None:
    user = await repository.create_user(
        email="alice@example.com", hashed_password="hash", full_name="Alice"
    )

    assert user.role == DEFAULT_USER_ROLE


async def test_an_explicit_role_is_persisted(repository: UserRepository) -> None:
    user = await repository.create_user(
        email="auditor@example.com",
        hashed_password="hash",
        full_name="Auditor",
        role="auditor",
    )

    assert user.role == "auditor"
    reloaded = await repository.get_user_by_email("auditor@example.com")
    assert reloaded is not None and reloaded.role == "auditor"


async def test_get_user_by_id_round_trips(repository: UserRepository) -> None:
    created = await repository.create_user(
        email="alice@example.com", hashed_password="hash", full_name="Alice"
    )

    fetched = await repository.get_user_by_id(created.id)

    assert fetched is not None
    assert fetched.email == "alice@example.com"


async def test_get_user_by_id_returns_none_when_missing(
    repository: UserRepository,
) -> None:
    assert await repository.get_user_by_id("does-not-exist") is None


async def test_set_user_role_updates_the_account(
    repository: UserRepository,
) -> None:
    created = await repository.create_user(
        email="alice@example.com", hashed_password="hash", full_name="Alice"
    )

    updated = await repository.set_user_role(created.id, role="auditor")

    assert updated.role == "auditor"
    reloaded = await repository.get_user_by_email("alice@example.com")
    assert reloaded is not None and reloaded.role == "auditor"


async def test_set_user_role_raises_for_an_unknown_account(
    repository: UserRepository,
) -> None:
    with pytest.raises(UserNotFoundError) as exc_info:
        await repository.set_user_role("does-not-exist", role="auditor")

    assert exc_info.value.user_id == "does-not-exist"


async def test_set_user_role_does_not_validate_the_role_itself(
    repository: UserRepository,
) -> None:
    # Deliberate: deciding whether a value names a real role is Layer
    # 3's job (`Role.parse`), and duplicating that check here would
    # create a second place for the policy to drift. Layer 2 never
    # passes an unvalidated string.
    created = await repository.create_user(
        email="alice@example.com", hashed_password="hash", full_name="Alice"
    )

    updated = await repository.set_user_role(created.id, role="not-a-real-role")

    assert updated.role == "not-a-real-role"
