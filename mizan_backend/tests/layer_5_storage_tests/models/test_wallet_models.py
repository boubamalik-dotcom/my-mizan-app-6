"""Tests for the Digital Wallet's SQLAlchemy ORM models (Layer 5):
optimistic locking, immutability enforcement, and database-level
invariants."""
from __future__ import annotations

from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.transaction_ledger_model import (
    LedgerEntryImmutableError,
    TransactionLedgerModel,
    TransactionType,
)
from src.layer_5_storage.models.wallet_model import WalletModel


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


class TestWalletModel:
    async def test_creates_wallet_with_zero_balance_defaults(
        self, session: AsyncSession
    ) -> None:
        wallet = WalletModel(owner_id="alice", currency="USD")
        session.add(wallet)
        await session.commit()

        assert wallet.id
        assert wallet.balance == Decimal("0")
        assert wallet.is_locked is False
        # SQLAlchemy's `version_id_col` mechanism stamps a version on
        # every flush, including the initial INSERT.
        assert wallet.version >= 1

    async def test_owner_currency_pair_must_be_unique(
        self, session: AsyncSession
    ) -> None:
        session.add(WalletModel(owner_id="alice", currency="USD"))
        await session.commit()

        session.add(WalletModel(owner_id="alice", currency="USD"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_negative_balance_is_rejected_by_check_constraint(
        self, session: AsyncSession
    ) -> None:
        session.add(WalletModel(owner_id="alice", currency="USD", balance=Decimal("-1")))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_version_increments_on_update(self, session: AsyncSession) -> None:
        wallet = WalletModel(owner_id="alice", currency="USD")
        session.add(wallet)
        await session.commit()
        version_after_insert = wallet.version

        wallet.balance = Decimal("50")
        await session.commit()
        assert wallet.version == version_after_insert + 1

    async def test_is_locked_can_be_toggled(self, session: AsyncSession) -> None:
        wallet = WalletModel(owner_id="alice", currency="USD")
        session.add(wallet)
        await session.commit()

        wallet.is_locked = True
        await session.commit()
        assert wallet.is_locked is True

    async def test_stale_version_write_raises_stale_data_error(self) -> None:
        # Two independent sessions over the same (in-memory, shared)
        # SQLite database simulate two transactions racing on the same
        # wallet row without any row lock — exactly the scenario
        # `version_id_col` exists to catch.
        engine = build_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = build_session_factory(engine)

        async with session_factory() as setup_session:
            wallet = WalletModel(owner_id="alice", currency="USD", balance=Decimal("100"))
            setup_session.add(wallet)
            await setup_session.commit()
            wallet_id = wallet.id

        async with session_factory() as session_a, session_factory() as session_b:
            wallet_a = await session_a.get(WalletModel, wallet_id)
            wallet_b = await session_b.get(WalletModel, wallet_id)
            assert wallet_a is not None and wallet_b is not None

            # Transaction A reads balance=100, computes a withdrawal of
            # 20, and commits first.
            wallet_a.balance = Decimal("80")
            await session_a.commit()

            # Transaction B also read balance=100 (before A committed)
            # and computes its own withdrawal of 30 — its write must be
            # rejected, not silently applied on top of A's already-
            # committed change (which would be a lost update).
            wallet_b.balance = Decimal("70")
            with pytest.raises(StaleDataError):
                await session_b.commit()

        await engine.dispose()


class TestTransactionLedgerModel:
    async def test_creates_entry_with_positive_amount(
        self, session: AsyncSession
    ) -> None:
        wallet = WalletModel(owner_id="alice", currency="USD", balance=Decimal("100"))
        session.add(wallet)
        await session.flush()

        entry = TransactionLedgerModel(
            wallet_id=wallet.id,
            amount=Decimal("50"),
            transaction_type=TransactionType.DEPOSIT,
        )
        session.add(entry)
        await session.commit()

        assert entry.id
        assert entry.created_at is not None

    async def test_non_positive_amount_is_rejected(self, session: AsyncSession) -> None:
        wallet = WalletModel(owner_id="alice", currency="USD")
        session.add(wallet)
        await session.flush()

        session.add(
            TransactionLedgerModel(
                wallet_id=wallet.id,
                amount=Decimal("0"),
                transaction_type=TransactionType.DEPOSIT,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_transfer_pair_shares_reference_id_and_counterparty(
        self, session: AsyncSession
    ) -> None:
        sender = WalletModel(owner_id="alice", currency="USD", balance=Decimal("100"))
        receiver = WalletModel(owner_id="bob", currency="USD", balance=Decimal("0"))
        session.add_all([sender, receiver])
        await session.flush()

        reference_id = "transfer-xyz"
        session.add_all(
            [
                TransactionLedgerModel(
                    wallet_id=sender.id,
                    amount=Decimal("40"),
                    transaction_type=TransactionType.TRANSFER,
                    reference_id=reference_id,
                    counterparty_wallet_id=receiver.id,
                ),
                TransactionLedgerModel(
                    wallet_id=receiver.id,
                    amount=Decimal("40"),
                    transaction_type=TransactionType.TRANSFER,
                    reference_id=reference_id,
                    counterparty_wallet_id=sender.id,
                ),
            ]
        )
        await session.commit()

        from sqlalchemy import select

        result = await session.execute(
            select(TransactionLedgerModel).where(
                TransactionLedgerModel.reference_id == reference_id
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 2
        assert {e.wallet_id for e in entries} == {sender.id, receiver.id}

    async def test_update_is_rejected_at_orm_level(self, session: AsyncSession) -> None:
        wallet = WalletModel(owner_id="alice", currency="USD")
        session.add(wallet)
        await session.flush()

        entry = TransactionLedgerModel(
            wallet_id=wallet.id,
            amount=Decimal("10"),
            transaction_type=TransactionType.DEPOSIT,
        )
        session.add(entry)
        await session.commit()

        entry.amount = Decimal("999")
        with pytest.raises(LedgerEntryImmutableError):
            await session.commit()

    async def test_delete_is_rejected_at_orm_level(self, session: AsyncSession) -> None:
        wallet = WalletModel(owner_id="alice", currency="USD")
        session.add(wallet)
        await session.flush()

        entry = TransactionLedgerModel(
            wallet_id=wallet.id,
            amount=Decimal("10"),
            transaction_type=TransactionType.DEPOSIT,
        )
        session.add(entry)
        await session.commit()

        await session.delete(entry)
        with pytest.raises(LedgerEntryImmutableError):
            await session.commit()
