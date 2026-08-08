"""Integration tests proving the Digital Wallet's optimistic locking
actually prevents lost updates under **genuine** concurrency — many
independent database connections, via a real local PostgreSQL server,
racing on the same wallet row.

SQLite (used elsewhere in this suite for speed/portability) funnels
every ``:memory:`` connection through a single shared connection, so
it cannot exercise true multi-connection concurrent access. These
tests are skipped automatically if no local Postgres server is
reachable at `WALLET_TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal
from typing import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_3_business.wallet.wallet_exceptions import InsufficientFundsError
from src.layer_3_business.wallet.wallet_service import WalletService
from src.layer_4_data_access.repositories.wallet_repository import (
    WalletConcurrencyConflictError,
)
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.transaction_ledger_model import TransactionType

WALLET_TEST_DATABASE_URL = os.environ.get(
    "WALLET_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/mizan_wallet_test",
)
# asyncpg (not SQLAlchemy's URL scheme) for the plain connectivity probe.
_ASYNCPG_URL = WALLET_TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

#: Generous but bounded — enough retries that a correctly-implemented
#: optimistic-locking retry loop always eventually succeeds under this
#: test's contention levels, without risking an infinite loop if
#: something is actually broken.
MAX_RETRIES = 20


async def _postgres_available() -> bool:
    try:
        connection = await asyncio.wait_for(asyncpg.connect(_ASYNCPG_URL), timeout=1.0)
        await connection.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not asyncio.run(_postgres_available()),
    reason="No local Postgres server reachable for concurrency integration test.",
)
pytestmark = requires_postgres


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = build_engine(WALLET_TEST_DATABASE_URL)
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return build_session_factory(engine)


@pytest.fixture
def wallet_service() -> WalletService:
    return WalletService()


async def _create_user(session_factory: async_sessionmaker, *, email: str) -> str:
    """Creates a user via the real `UnitOfWork`/`UserRepository` path
    and returns its id — `WalletModel.user_id` is a real foreign key
    into `users.id`, enforced by Postgres just as strictly as by
    SQLite (`db_config.build_engine` turns on `PRAGMA foreign_keys` for
    SQLite specifically to match)."""
    async with UnitOfWork(session_factory) as uow:
        user = await uow.users.create_user(
            email=email, hashed_password="hashed", full_name="Test User"
        )
        await uow.commit()
    return user.id


@pytest_asyncio.fixture
async def user_id(session_factory: async_sessionmaker) -> str:
    return await _create_user(session_factory, email="alice@example.com")


@pytest_asyncio.fixture
async def other_user_id(session_factory: async_sessionmaker) -> str:
    return await _create_user(session_factory, email="bob@example.com")


async def _deposit_with_retry(
    session_factory: async_sessionmaker,
    wallet_service: WalletService,
    wallet_id: str,
    amount: Decimal,
) -> None:
    """Mirrors what a real Layer 2 controller does: read, compute via
    Layer 3, write via Layer 4, and retry from a fresh read on an
    optimistic-lock conflict."""
    for _ in range(MAX_RETRIES):
        async with UnitOfWork(session_factory) as uow:
            wallet = await uow.wallets.get_wallet_by_id(wallet_id)
            assert wallet is not None
            new_balance = wallet_service.calculate_balance_after_deposit(
                wallet.balance, amount
            )
            try:
                await uow.wallets.update_wallet_balance(
                    wallet_id, new_balance, expected_version=wallet.version
                )
                await uow.wallets.append_ledger_entry(
                    wallet_id=wallet_id,
                    amount=amount,
                    transaction_type=TransactionType.DEPOSIT,
                )
                await uow.commit()
                return
            except WalletConcurrencyConflictError:
                continue
    raise AssertionError(f"Exceeded {MAX_RETRIES} retries for a deposit.")


async def _withdraw_with_retry(
    session_factory: async_sessionmaker,
    wallet_service: WalletService,
    wallet_id: str,
    amount: Decimal,
) -> bool:
    """Same retry pattern as `_deposit_with_retry`, but returns
    whether the withdrawal succeeded (`False` on
    `InsufficientFundsError`, which is a legitimate business-rule
    rejection, not a concurrency conflict, and must never be
    retried)."""
    for _ in range(MAX_RETRIES):
        async with UnitOfWork(session_factory) as uow:
            wallet = await uow.wallets.get_wallet_by_id(wallet_id)
            assert wallet is not None
            try:
                new_balance = wallet_service.calculate_balance_after_withdrawal(
                    wallet.balance, amount
                )
            except InsufficientFundsError:
                return False

            try:
                await uow.wallets.update_wallet_balance(
                    wallet_id, new_balance, expected_version=wallet.version
                )
                await uow.wallets.append_ledger_entry(
                    wallet_id=wallet_id,
                    amount=amount,
                    transaction_type=TransactionType.WITHDRAWAL,
                )
                await uow.commit()
                return True
            except WalletConcurrencyConflictError:
                continue
    raise AssertionError(f"Exceeded {MAX_RETRIES} retries for a withdrawal.")


async def test_concurrent_deposits_never_lose_an_update(
    session_factory: async_sessionmaker, wallet_service: WalletService, user_id: str
) -> None:
    """20 concurrent tasks, each depositing 10.00 into the *same*
    wallet via genuinely independent database connections. Without
    optimistic locking (or any concurrency control at all), some of
    these read-modify-write cycles would race and clobber each other,
    landing on a final balance less than the true sum. With it, every
    single deposit is guaranteed to be reflected."""
    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        await uow.commit()

    deposit_amount = Decimal("10.00")
    concurrent_deposits = 20

    await asyncio.gather(
        *[
            _deposit_with_retry(session_factory, wallet_service, wallet.id, deposit_amount)
            for _ in range(concurrent_deposits)
        ]
    )

    async with UnitOfWork(session_factory) as uow:
        final = await uow.wallets.get_wallet_by_id(wallet.id)
    assert final is not None
    assert final.balance == deposit_amount * concurrent_deposits


async def test_concurrent_withdrawals_never_overdraw(
    session_factory: async_sessionmaker, wallet_service: WalletService, user_id: str
) -> None:
    """20 concurrent withdrawal attempts of 30.00 each against a
    wallet that only holds 100.00 — enough funds for exactly 3 to
    succeed. Every one of the 20 tasks races against real, independent
    Postgres connections; the assertions below hold regardless of
    which 3 happen to "win"."""
    initial_balance = Decimal("100.00")
    withdrawal_amount = Decimal("30.00")
    concurrent_withdrawals = 20
    expected_successes = int(initial_balance // withdrawal_amount)  # 3

    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        await uow.wallets.update_wallet_balance(
            wallet.id, initial_balance, expected_version=wallet.version
        )
        await uow.commit()

    results = await asyncio.gather(
        *[
            _withdraw_with_retry(session_factory, wallet_service, wallet.id, withdrawal_amount)
            for _ in range(concurrent_withdrawals)
        ]
    )

    successful = sum(1 for succeeded in results if succeeded)
    assert successful == expected_successes

    async with UnitOfWork(session_factory) as uow:
        final = await uow.wallets.get_wallet_by_id(wallet.id)
    assert final is not None
    # The core overdraft guarantee: the balance never goes negative,
    # no matter how many concurrent withdrawal attempts raced for it.
    assert final.balance == initial_balance - (withdrawal_amount * successful)
    assert final.balance >= Decimal("0")


async def test_concurrent_transfers_conserve_total_funds_across_two_wallets(
    session_factory: async_sessionmaker,
    wallet_service: WalletService,
    user_id: str,
    other_user_id: str,
) -> None:
    """10 concurrent transfers of 5.00 from wallet A to wallet B, and
    10 concurrent transfers of 5.00 in the *opposite* direction (B to
    A) — all racing simultaneously against real Postgres connections.
    Regardless of ordering/interleaving, the total funds held across
    both wallets must be exactly conserved, and neither wallet may
    ever go negative."""

    async def transfer_with_retry(sender_id: str, receiver_id: str, amount: Decimal) -> None:
        for _ in range(MAX_RETRIES):
            try:
                async with UnitOfWork(session_factory) as uow:
                    sender = await uow.wallets.get_wallet_by_id(sender_id)
                    receiver = await uow.wallets.get_wallet_by_id(receiver_id)
                    assert sender is not None and receiver is not None

                    try:
                        new_sender_balance, new_receiver_balance = (
                            wallet_service.calculate_balances_after_transfer(
                                sender.balance, receiver.balance, amount
                            )
                        )
                    except InsufficientFundsError:
                        return  # a legitimate rejection, not a conflict

                    reference_id = str(uuid.uuid4())
                    # Updating both wallets in a fixed, deterministic
                    # order (ascending id) — rather than "sender first"
                    # — is the standard fix for the lock-ordering
                    # deadlock two *opposite-direction* concurrent
                    # transfers between the same pair of wallets would
                    # otherwise risk at the database level. This is a
                    # test-side (i.e. caller-side) concern: nothing
                    # about `WalletRepository.update_wallet_balance`
                    # itself dictates *which* wallet a caller updates
                    # first.
                    first_id, second_id = sorted([sender_id, receiver_id])
                    first_balance, second_balance = (
                        (new_sender_balance, new_receiver_balance)
                        if first_id == sender_id
                        else (new_receiver_balance, new_sender_balance)
                    )
                    first_version, second_version = (
                        (sender.version, receiver.version)
                        if first_id == sender_id
                        else (receiver.version, sender.version)
                    )
                    await uow.wallets.update_wallet_balance(
                        first_id, first_balance, expected_version=first_version
                    )
                    await uow.wallets.update_wallet_balance(
                        second_id, second_balance, expected_version=second_version
                    )
                    await uow.wallets.append_ledger_entry(
                        wallet_id=sender_id,
                        amount=amount,
                        transaction_type=TransactionType.TRANSFER,
                        reference_id=reference_id,
                        counterparty_wallet_id=receiver_id,
                    )
                    await uow.wallets.append_ledger_entry(
                        wallet_id=receiver_id,
                        amount=amount,
                        transaction_type=TransactionType.TRANSFER,
                        reference_id=reference_id,
                        counterparty_wallet_id=sender_id,
                    )
                    await uow.commit()
                    return
            except WalletConcurrencyConflictError:
                continue
        raise AssertionError(f"Exceeded {MAX_RETRIES} retries for a transfer.")

    async with UnitOfWork(session_factory) as uow:
        wallet_a = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        wallet_b = await uow.wallets.create_wallet(user_id=other_user_id, currency="USD")
        await uow.wallets.update_wallet_balance(
            wallet_a.id, Decimal("100.00"), expected_version=wallet_a.version
        )
        await uow.wallets.update_wallet_balance(
            wallet_b.id, Decimal("100.00"), expected_version=wallet_b.version
        )
        await uow.commit()

    total_before = Decimal("200.00")
    transfer_amount = Decimal("5.00")

    tasks = [
        transfer_with_retry(wallet_a.id, wallet_b.id, transfer_amount) for _ in range(10)
    ] + [
        transfer_with_retry(wallet_b.id, wallet_a.id, transfer_amount) for _ in range(10)
    ]
    await asyncio.gather(*tasks)

    async with UnitOfWork(session_factory) as uow:
        final_a = await uow.wallets.get_wallet_by_id(wallet_a.id)
        final_b = await uow.wallets.get_wallet_by_id(wallet_b.id)
    assert final_a is not None and final_b is not None
    assert final_a.balance >= Decimal("0")
    assert final_b.balance >= Decimal("0")
    assert final_a.balance + final_b.balance == total_before
