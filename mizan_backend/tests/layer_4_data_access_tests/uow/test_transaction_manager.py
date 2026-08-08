"""Tests for the asynchronous `UnitOfWork` (Layer 4): commit/rollback
semantics and the atomicity guarantee across multiple repository
operations."""
from __future__ import annotations

from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_4_data_access.repositories.wallet_repository import (
    WalletConcurrencyConflictError,
)
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.transaction_ledger_model import TransactionType


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return build_session_factory(engine)


@pytest_asyncio.fixture
async def user_id(session_factory: async_sessionmaker) -> str:
    """Creates a user via the same `UnitOfWork`/`UserRepository` path
    real code uses, so every wallet in this test file is linked to a
    genuinely-persisted account, satisfying `WalletModel.user_id`'s
    foreign key."""
    async with UnitOfWork(session_factory) as uow:
        user = await uow.users.create_user(
            email="alice@example.com", hashed_password="hashed", full_name="Alice"
        )
        await uow.commit()
    return user.id


async def test_commit_persists_changes_across_a_fresh_unit_of_work(
    session_factory: async_sessionmaker, user_id: str
) -> None:
    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        reloaded = await uow.wallets.get_wallet_by_id(wallet.id)
    assert reloaded is not None
    assert reloaded.user_id == user_id


async def test_uncommitted_work_is_invisible_to_a_later_unit_of_work(
    session_factory: async_sessionmaker, user_id: str
) -> None:
    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        # Deliberately never call uow.commit().

    async with UnitOfWork(session_factory) as uow:
        reloaded = await uow.wallets.get_wallet_by_id(wallet.id)
    assert reloaded is None


async def test_exception_inside_the_block_rolls_back_automatically(
    session_factory: async_sessionmaker, user_id: str
) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with UnitOfWork(session_factory) as uow:
            wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
            raise RuntimeError("boom")

    async with UnitOfWork(session_factory) as uow:
        reloaded = await uow.wallets.get_wallet_by_id(wallet.id)
    assert reloaded is None


async def test_balance_update_and_ledger_entry_commit_together_atomically(
    session_factory: async_sessionmaker, user_id: str
) -> None:
    """The core ACID guarantee this Unit of Work exists for: a
    wallet's balance mutation and its corresponding ledger entry are
    always committed together, never one without the other."""
    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        await uow.wallets.update_wallet_balance(
            wallet.id, Decimal("100"), expected_version=wallet.version
        )
        await uow.wallets.append_ledger_entry(
            wallet_id=wallet.id,
            amount=Decimal("100"),
            transaction_type=TransactionType.DEPOSIT,
        )
        await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        reloaded = await uow.wallets.get_wallet_by_id(wallet.id)
        assert reloaded is not None
        assert reloaded.balance == Decimal("100")


async def test_explicit_rollback_discards_changes_without_raising(
    session_factory: async_sessionmaker, user_id: str
) -> None:
    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        await uow.wallets.update_wallet_balance(
            wallet.id, Decimal("100"), expected_version=wallet.version
        )
        await uow.rollback()
        # The unit of work is still usable for reads after an explicit
        # rollback; only the mutation is discarded.

    async with UnitOfWork(session_factory) as uow:
        reloaded = await uow.wallets.get_wallet_by_id(wallet.id)
    assert reloaded is None  # even the wallet creation itself was rolled back


async def test_commit_outside_active_transaction_raises(
    session_factory: async_sessionmaker,
) -> None:
    uow = UnitOfWork(session_factory)
    with pytest.raises(RuntimeError):
        await uow.commit()


async def test_rollback_outside_active_transaction_is_a_safe_no_op(
    session_factory: async_sessionmaker,
) -> None:
    uow = UnitOfWork(session_factory)
    await uow.rollback()  # must not raise


async def test_atomicity_when_second_operation_fails_mid_transaction(
    session_factory: async_sessionmaker, user_id: str
) -> None:
    """If the ledger append fails partway through a unit of work (e.g.
    because the wallet id it names does not exist), the balance update
    that already happened earlier in the *same, uncommitted*
    transaction must not survive either."""
    async with UnitOfWork(session_factory) as setup_uow:
        wallet = await setup_uow.wallets.create_wallet(user_id=user_id, currency="USD")
        await setup_uow.commit()

    with pytest.raises(Exception):
        async with UnitOfWork(session_factory) as uow:
            await uow.wallets.update_wallet_balance(
                wallet.id, Decimal("500"), expected_version=wallet.version
            )
            # This second operation fails (foreign key violation) —
            # the whole block must roll back, including the balance
            # update above.
            await uow.wallets.append_ledger_entry(
                wallet_id="does-not-exist",
                amount=Decimal("500"),
                transaction_type=TransactionType.DEPOSIT,
            )
            await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        reloaded = await uow.wallets.get_wallet_by_id(wallet.id)
    assert reloaded is not None
    assert reloaded.balance == Decimal("0")  # the update never took effect


async def test_two_units_of_work_do_not_share_transactional_state(
    session_factory: async_sessionmaker, user_id: str
) -> None:
    """Each `UnitOfWork` opens its own session/transaction — a
    conflict detected in one must not be affected by another."""
    async with UnitOfWork(session_factory) as setup_uow:
        wallet = await setup_uow.wallets.create_wallet(user_id=user_id, currency="USD")
        await setup_uow.commit()

    async with UnitOfWork(session_factory) as uow_a, UnitOfWork(session_factory) as uow_b:
        wallet_in_a = await uow_a.wallets.get_wallet_by_id(wallet.id)
        wallet_in_b = await uow_b.wallets.get_wallet_by_id(wallet.id)
        assert wallet_in_a is not None and wallet_in_b is not None

        await uow_a.wallets.update_wallet_balance(
            wallet.id, Decimal("10"), expected_version=wallet_in_a.version
        )
        await uow_a.commit()

        with pytest.raises(WalletConcurrencyConflictError):
            await uow_b.wallets.update_wallet_balance(
                wallet.id, Decimal("20"), expected_version=wallet_in_b.version
            )
