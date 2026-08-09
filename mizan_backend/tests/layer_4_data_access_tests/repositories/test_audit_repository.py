"""Functional tests for `AuditRepository` (Layer 4): filtering,
stable pagination, owner attribution, and the read-only surface that
keeps an audit from being able to alter what it audits.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.layer_4_data_access.repositories.audit_repository import (
    AuditLedgerEntry,
    AuditRepository,
)
from src.layer_4_data_access.repositories.wallet_repository import WalletRepository
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.transaction_ledger_model import (
    EntryDirection,
    TransactionLedgerModel,
    TransactionType,
)
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
def audit(session: AsyncSession) -> AuditRepository:
    return AuditRepository(session)


@pytest.fixture
def wallets(session: AsyncSession) -> WalletRepository:
    return WalletRepository(session)


async def _create_user(session: AsyncSession, *, email: str) -> UserModel:
    user = UserModel(email=email, hashed_password="hashed", full_name="Test User")
    session.add(user)
    await session.flush()
    return user


async def _entry(
    session: AsyncSession,
    *,
    wallet_id: str,
    amount: str,
    transaction_type: TransactionType = TransactionType.DEPOSIT,
    direction: EntryDirection | None = EntryDirection.CREDIT,
    reference_id: str | None = None,
    counterparty_wallet_id: str | None = None,
    created_at: datetime | None = None,
) -> TransactionLedgerModel:
    """Writes a ledger row directly, so a test can place entries in
    time and construct legacy rows that predate the direction column."""
    entry = TransactionLedgerModel(
        wallet_id=wallet_id,
        amount=Decimal(amount),
        transaction_type=transaction_type,
        direction=direction,
        reference_id=reference_id,
        counterparty_wallet_id=counterparty_wallet_id,
    )
    if created_at is not None:
        entry.created_at = created_at
    session.add(entry)
    await session.flush()
    return entry


class TestQueryLedger:
    async def test_returns_every_entry_with_its_owner_attached(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        await _entry(session, wallet_id=wallet.id, amount="100")

        page = await audit.query_ledger()

        assert page.total == 1
        entry = page.entries[0]
        assert isinstance(entry, AuditLedgerEntry)
        assert entry.wallet_id == wallet.id
        # Resolved server-side so an auditor can attribute an entry
        # without a second lookup.
        assert entry.user_id == user.id
        assert entry.amount == Decimal("100")

    async def test_filters_by_wallet(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        user = await _create_user(session, email="owner@example.com")
        first = await wallets.create_wallet(user_id=user.id, currency="DZD")
        second = await wallets.create_wallet(user_id=user.id, currency="USD")
        await _entry(session, wallet_id=first.id, amount="10")
        await _entry(session, wallet_id=second.id, amount="20")

        page = await audit.query_ledger(wallet_id=first.id)

        assert [e.wallet_id for e in page.entries] == [first.id]
        assert page.total == 1

    async def test_filters_by_user_across_all_their_wallets(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        alice = await _create_user(session, email="alice@example.com")
        bob = await _create_user(session, email="bob@example.com")
        alice_dzd = await wallets.create_wallet(user_id=alice.id, currency="DZD")
        alice_usd = await wallets.create_wallet(user_id=alice.id, currency="USD")
        bob_wallet = await wallets.create_wallet(user_id=bob.id, currency="DZD")
        await _entry(session, wallet_id=alice_dzd.id, amount="10")
        await _entry(session, wallet_id=alice_usd.id, amount="20")
        await _entry(session, wallet_id=bob_wallet.id, amount="30")

        page = await audit.query_ledger(user_id=alice.id)

        assert page.total == 2
        assert {e.user_id for e in page.entries} == {alice.id}

    async def test_filters_by_transaction_type(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        await _entry(session, wallet_id=wallet.id, amount="10")
        await _entry(
            session,
            wallet_id=wallet.id,
            amount="5",
            transaction_type=TransactionType.WITHDRAWAL,
            direction=EntryDirection.DEBIT,
        )

        page = await audit.query_ledger(
            transaction_type=TransactionType.WITHDRAWAL
        )

        assert [e.amount for e in page.entries] == [Decimal("5")]

    async def test_filters_by_time_window_inclusively(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        base = datetime(2026, 1, 10, 12, 0, 0)
        await _entry(
            session, wallet_id=wallet.id, amount="1", created_at=base - timedelta(days=1)
        )
        await _entry(session, wallet_id=wallet.id, amount="2", created_at=base)
        await _entry(
            session, wallet_id=wallet.id, amount="3", created_at=base + timedelta(days=1)
        )

        page = await audit.query_ledger(occurred_from=base, occurred_to=base)

        assert [e.amount for e in page.entries] == [Decimal("2")]

    async def test_reports_the_total_beyond_the_page(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        for index in range(5):
            await _entry(session, wallet_id=wallet.id, amount=str(index + 1))

        page = await audit.query_ledger(limit=2)

        assert len(page.entries) == 2
        # So a caller knows how much history is left without walking it.
        assert page.total == 5

    async def test_pagination_is_stable_across_pages(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        # Entries written inside one transaction can share a timestamp
        # to the resolution the column stores; without the id
        # tie-break, paging could skip or repeat rows.
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        identical = datetime(2026, 1, 10, 12, 0, 0)
        for index in range(6):
            await _entry(
                session,
                wallet_id=wallet.id,
                amount=str(index + 1),
                created_at=identical,
            )

        first = await audit.query_ledger(limit=3, offset=0)
        second = await audit.query_ledger(limit=3, offset=3)

        ids = [e.id for e in first.entries] + [e.id for e in second.entries]
        assert len(set(ids)) == 6, "a paged export skipped or repeated an entry"


class TestDirectionResolution:
    async def test_reads_back_the_recorded_direction(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        await _entry(
            session,
            wallet_id=wallet.id,
            amount="5",
            transaction_type=TransactionType.WITHDRAWAL,
            direction=EntryDirection.DEBIT,
        )

        page = await audit.query_ledger()

        assert page.entries[0].direction is EntryDirection.DEBIT

    @pytest.mark.parametrize(
        ("transaction_type", "expected"),
        [
            (TransactionType.DEPOSIT, EntryDirection.CREDIT),
            (TransactionType.WITHDRAWAL, EntryDirection.DEBIT),
        ],
    )
    async def test_infers_direction_for_legacy_deposits_and_withdrawals(
        self,
        session: AsyncSession,
        audit: AuditRepository,
        wallets: WalletRepository,
        transaction_type: TransactionType,
        expected: EntryDirection,
    ) -> None:
        # Rows written before the column existed cannot be backfilled —
        # the ledger is append-only — but these two types are
        # unambiguous from the type alone.
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        await _entry(
            session,
            wallet_id=wallet.id,
            amount="5",
            transaction_type=transaction_type,
            direction=None,
        )

        page = await audit.query_ledger()

        assert page.entries[0].direction is expected

    async def test_leaves_a_legacy_transfer_unresolved(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        # Both legs share a type and a positive amount, so the
        # direction is genuinely unrecoverable. Inventing one would put
        # a fabricated number in an audit report.
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        await _entry(
            session,
            wallet_id=wallet.id,
            amount="5",
            transaction_type=TransactionType.TRANSFER,
            direction=None,
        )

        page = await audit.query_ledger()

        assert page.entries[0].direction is None


class TestWholeHistoryAndTransfers:
    async def test_lists_a_wallet_s_complete_history_oldest_first(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        base = datetime(2026, 1, 10, 12, 0, 0)
        for index in range(3):
            await _entry(
                session,
                wallet_id=wallet.id,
                amount=str(index + 1),
                created_at=base + timedelta(minutes=index),
            )

        entries = await audit.list_all_entries_for_wallet(wallet.id)

        assert [e.amount for e in entries] == [
            Decimal("1"),
            Decimal("2"),
            Decimal("3"),
        ]

    async def test_the_complete_history_is_not_capped_by_a_page_size(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        # Reconciling against a partial history would produce a
        # discrepancy that means nothing.
        user = await _create_user(session, email="owner@example.com")
        wallet = await wallets.create_wallet(user_id=user.id, currency="DZD")
        for index in range(120):
            await _entry(session, wallet_id=wallet.id, amount="1")

        entries = await audit.list_all_entries_for_wallet(wallet.id)

        assert len(entries) == 120

    async def test_reconstructs_both_legs_of_a_transfer(
        self, session: AsyncSession, audit: AuditRepository, wallets: WalletRepository
    ) -> None:
        alice = await _create_user(session, email="alice@example.com")
        bob = await _create_user(session, email="bob@example.com")
        source = await wallets.create_wallet(user_id=alice.id, currency="DZD")
        destination = await wallets.create_wallet(user_id=bob.id, currency="DZD")
        await _entry(
            session,
            wallet_id=source.id,
            amount="40",
            transaction_type=TransactionType.TRANSFER,
            direction=EntryDirection.DEBIT,
            reference_id="ref-1",
            counterparty_wallet_id=destination.id,
        )
        await _entry(
            session,
            wallet_id=destination.id,
            amount="40",
            transaction_type=TransactionType.TRANSFER,
            direction=EntryDirection.CREDIT,
            reference_id="ref-1",
            counterparty_wallet_id=source.id,
        )
        await _entry(session, wallet_id=source.id, amount="5", reference_id="ref-2")

        entries = await audit.list_entries_by_reference("ref-1")

        assert len(entries) == 2
        assert {e.direction for e in entries} == {
            EntryDirection.DEBIT,
            EntryDirection.CREDIT,
        }
        # Attribution across two different owners in one view.
        assert {e.user_id for e in entries} == {alice.id, bob.id}

    async def test_an_unknown_reference_yields_nothing(
        self, audit: AuditRepository
    ) -> None:
        assert await audit.list_entries_by_reference("no-such-ref") == []


class TestTheAuditPathCannotWrite:
    def test_exposes_no_mutating_method(self) -> None:
        # The guarantee is structural: an audit request cannot alter
        # the evidence it inspects, because there is no method to do it
        # with.
        surface = {
            name for name in dir(AuditRepository) if not name.startswith("_")
        }

        assert surface == {
            "query_ledger",
            "list_all_entries_for_wallet",
            "list_entries_by_reference",
        }
