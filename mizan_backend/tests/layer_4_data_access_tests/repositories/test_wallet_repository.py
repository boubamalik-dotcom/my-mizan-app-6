"""Functional tests for `WalletRepository` (Layer 4): mapping between
ORM rows and plain-data records, the optimistic-lock check it performs
before ever writing a balance, and the `user_id` foreign-key link to
an owning account.

(Genuine *concurrent* locking behaviour — many independent database
connections racing on the same wallet — is covered separately, against
a real Postgres server, in
`tests/integration_tests/test_wallet_concurrency.py`; SQLite's
single-connection-per-`:memory:`-database model can't exercise that.)
"""
from __future__ import annotations

from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.layer_4_data_access.repositories.wallet_repository import (
    LedgerEntryRecord,
    WalletConcurrencyConflictError,
    WalletNotFoundError,
    WalletRecord,
    WalletRepository,
)
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.transaction_ledger_model import TransactionType
from src.layer_5_storage.models.user_model import UserModel


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.fixture
def repository(session: AsyncSession) -> WalletRepository:
    return WalletRepository(session)


async def _create_user(session: AsyncSession, *, email: str) -> UserModel:
    user = UserModel(email=email, hashed_password="hashed", full_name="Test User")
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def user_id(session: AsyncSession) -> str:
    user = await _create_user(session, email="alice@example.com")
    return user.id


@pytest_asyncio.fixture
async def other_user_id(session: AsyncSession) -> str:
    user = await _create_user(session, email="bob@example.com")
    return user.id


class TestCreateAndGetWallet:
    async def test_create_wallet_returns_zero_balance_unlocked_record(
        self, repository: WalletRepository, user_id: str
    ) -> None:
        record = await repository.create_wallet(user_id=user_id, currency="USD")

        assert isinstance(record, WalletRecord)
        assert record.id
        assert record.user_id == user_id
        assert record.currency == "USD"
        assert record.balance == Decimal("0")
        assert record.is_locked is False
        assert record.version >= 1

    async def test_get_wallet_by_id_round_trips(
        self, repository: WalletRepository, user_id: str
    ) -> None:
        created = await repository.create_wallet(user_id=user_id, currency="USD")

        fetched = await repository.get_wallet_by_id(created.id)
        assert fetched == created

    async def test_get_wallet_by_id_returns_none_when_missing(
        self, repository: WalletRepository
    ) -> None:
        assert await repository.get_wallet_by_id("does-not-exist") is None

    async def test_create_wallet_rejects_a_nonexistent_user_id(
        self, repository: WalletRepository
    ) -> None:
        with pytest.raises(Exception):  # sqlite/postgres IntegrityError
            await repository.create_wallet(user_id="does-not-exist", currency="USD")


class TestUpdateWalletBalance:
    async def test_updates_balance_and_increments_version(
        self, repository: WalletRepository, user_id: str
    ) -> None:
        wallet = await repository.create_wallet(user_id=user_id, currency="USD")

        updated = await repository.update_wallet_balance(
            wallet.id, Decimal("150.00"), expected_version=wallet.version
        )

        assert updated.balance == Decimal("150.00")
        assert updated.version == wallet.version + 1

        reloaded = await repository.get_wallet_by_id(wallet.id)
        assert reloaded is not None
        assert reloaded.balance == Decimal("150.00")

    async def test_raises_not_found_for_missing_wallet(
        self, repository: WalletRepository
    ) -> None:
        with pytest.raises(WalletNotFoundError):
            await repository.update_wallet_balance(
                "does-not-exist", Decimal("10"), expected_version=1
            )

    async def test_raises_conflict_for_stale_expected_version(
        self, repository: WalletRepository, user_id: str
    ) -> None:
        wallet = await repository.create_wallet(user_id=user_id, currency="USD")

        # First writer succeeds and bumps the version.
        await repository.update_wallet_balance(
            wallet.id, Decimal("10"), expected_version=wallet.version
        )

        # A second attempt using the *original*, now-stale version must
        # be rejected rather than silently overwriting the first
        # writer's change (a lost update).
        with pytest.raises(WalletConcurrencyConflictError):
            await repository.update_wallet_balance(
                wallet.id, Decimal("999"), expected_version=wallet.version
            )

        # And the first writer's change must still be intact.
        reloaded = await repository.get_wallet_by_id(wallet.id)
        assert reloaded is not None
        assert reloaded.balance == Decimal("10")


class TestSetWalletLocked:
    async def test_locks_and_unlocks_a_wallet(
        self, repository: WalletRepository, user_id: str
    ) -> None:
        wallet = await repository.create_wallet(user_id=user_id, currency="USD")

        locked = await repository.set_wallet_locked(wallet.id, is_locked=True)
        assert locked.is_locked is True

        unlocked = await repository.set_wallet_locked(wallet.id, is_locked=False)
        assert unlocked.is_locked is False

    async def test_raises_not_found_for_missing_wallet(
        self, repository: WalletRepository
    ) -> None:
        with pytest.raises(WalletNotFoundError):
            await repository.set_wallet_locked("does-not-exist", is_locked=True)


class TestAppendLedgerEntry:
    async def test_appends_and_returns_a_record(
        self, repository: WalletRepository, user_id: str
    ) -> None:
        wallet = await repository.create_wallet(user_id=user_id, currency="USD")

        entry = await repository.append_ledger_entry(
            wallet_id=wallet.id,
            amount=Decimal("25"),
            transaction_type=TransactionType.DEPOSIT,
        )

        assert isinstance(entry, LedgerEntryRecord)
        assert entry.id
        assert entry.wallet_id == wallet.id
        assert entry.amount == Decimal("25")
        assert entry.transaction_type is TransactionType.DEPOSIT
        assert entry.created_at is not None

    async def test_transfer_entry_carries_reference_and_counterparty(
        self, repository: WalletRepository, user_id: str, other_user_id: str
    ) -> None:
        sender = await repository.create_wallet(user_id=user_id, currency="USD")
        receiver = await repository.create_wallet(user_id=other_user_id, currency="USD")

        debit = await repository.append_ledger_entry(
            wallet_id=sender.id,
            amount=Decimal("40"),
            transaction_type=TransactionType.TRANSFER,
            reference_id="transfer-1",
            counterparty_wallet_id=receiver.id,
        )
        credit = await repository.append_ledger_entry(
            wallet_id=receiver.id,
            amount=Decimal("40"),
            transaction_type=TransactionType.TRANSFER,
            reference_id="transfer-1",
            counterparty_wallet_id=sender.id,
        )

        assert debit.reference_id == credit.reference_id == "transfer-1"
        assert debit.counterparty_wallet_id == receiver.id
        assert credit.counterparty_wallet_id == sender.id

    async def test_raises_not_found_for_nonexistent_wallet(
        self, repository: WalletRepository
    ) -> None:
        with pytest.raises(WalletNotFoundError):
            await repository.append_ledger_entry(
                wallet_id="does-not-exist",
                amount=Decimal("10"),
                transaction_type=TransactionType.DEPOSIT,
            )
