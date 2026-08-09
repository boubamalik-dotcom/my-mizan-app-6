"""Layer 4 — read-only repository over the append-only transaction
ledger, for regulatory inspection.

Deliberately separate from `WalletRepository`, which exists to *write*
the ledger as a side effect of moving money. This one only ever reads,
and exposes no method that could append, amend, or delete an entry —
so "the audit path cannot alter the thing it audits" is a property of
the class's surface area, not a convention reviewers must remember.

Like every Layer 4 repository, it returns plain dataclasses rather
than ORM objects, so Layers 2 and 3 never see SQLAlchemy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...layer_5_storage.models.transaction_ledger_model import (
    EntryDirection,
    TransactionLedgerModel,
    TransactionType,
)
from ...layer_5_storage.models.wallet_model import WalletModel


@dataclass(frozen=True, slots=True)
class AuditLedgerEntry:
    """An immutable snapshot of one ledger entry, enriched with the
    owning wallet's user so an auditor can attribute it without a
    second query."""

    id: str
    wallet_id: str
    user_id: str
    amount: Decimal
    transaction_type: TransactionType
    direction: Optional[EntryDirection]
    reference_id: Optional[str]
    counterparty_wallet_id: Optional[str]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditLedgerPage:
    """One page of ledger entries plus the total matching the query, so
    a caller can tell how much history is left without walking it."""

    entries: List[AuditLedgerEntry]
    total: int


class AuditRepository:
    """Async, read-only repository over the transaction ledger.

    Bound to a single `AsyncSession` for its lifetime, like every other
    Layer 4 repository.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: The `AsyncSession` used for every read. This
                repository never writes, so it never needs the caller
                to commit.
        """
        self._session = session

    async def query_ledger(
        self,
        *,
        wallet_id: Optional[str] = None,
        user_id: Optional[str] = None,
        transaction_type: Optional[TransactionType] = None,
        occurred_from: Optional[datetime] = None,
        occurred_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditLedgerPage:
        """Returns the ledger entries matching every supplied filter.

        Ordered oldest-first, and tie-broken by `id`: entries written
        inside one transaction can share a timestamp to the resolution
        the column stores, and an unstable order would make a paginated
        export silently skip or repeat rows across pages.

        Args:
            wallet_id: Restrict to one wallet.
            user_id: Restrict to every wallet owned by one user.
            transaction_type: Restrict to deposits, withdrawals, or
                transfers.
            occurred_from: Inclusive lower bound on `created_at`.
            occurred_to: Inclusive upper bound on `created_at`.
            limit: Page size.
            offset: Entries to skip.

        Returns:
            An [AuditLedgerPage] of matching entries and the total
            count.
        """
        base = select(TransactionLedgerModel).join(
            WalletModel, WalletModel.id == TransactionLedgerModel.wallet_id
        )
        base = self._apply_filters(
            base,
            wallet_id=wallet_id,
            user_id=user_id,
            transaction_type=transaction_type,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )

        count_statement = select(func.count()).select_from(base.subquery())
        total = await self._session.scalar(count_statement) or 0

        page_statement = (
            base.add_columns(WalletModel.user_id)
            .order_by(
                TransactionLedgerModel.created_at.asc(),
                TransactionLedgerModel.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(page_statement)

        entries = [
            self._to_entry(row_entry, user_id=row_user_id)
            for row_entry, row_user_id in result.all()
        ]
        return AuditLedgerPage(entries=entries, total=total)

    async def list_all_entries_for_wallet(
        self, wallet_id: str
    ) -> Sequence[AuditLedgerEntry]:
        """Returns a wallet's **complete** ledger, oldest first.

        Unpaginated by design: this feeds
        `AuditService.verify_ledger_integrity`, and reconciling a
        balance against a partial history would produce a discrepancy
        that means nothing. Callers wanting a page should use
        [query_ledger] instead.
        """
        statement = (
            select(TransactionLedgerModel, WalletModel.user_id)
            .join(WalletModel, WalletModel.id == TransactionLedgerModel.wallet_id)
            .where(TransactionLedgerModel.wallet_id == wallet_id)
            .order_by(
                TransactionLedgerModel.created_at.asc(),
                TransactionLedgerModel.id.asc(),
            )
        )
        result = await self._session.execute(statement)
        return [
            self._to_entry(entry, user_id=owner_id)
            for entry, owner_id in result.all()
        ]

    async def list_entries_by_reference(
        self, reference_id: str
    ) -> Sequence[AuditLedgerEntry]:
        """Returns every entry sharing `reference_id`, oldest first.

        A transfer writes one entry per side under a shared reference,
        so this reconstructs both legs of a movement between wallets —
        the view an investigator needs to follow money across accounts.
        """
        statement = (
            select(TransactionLedgerModel, WalletModel.user_id)
            .join(WalletModel, WalletModel.id == TransactionLedgerModel.wallet_id)
            .where(TransactionLedgerModel.reference_id == reference_id)
            .order_by(
                TransactionLedgerModel.created_at.asc(),
                TransactionLedgerModel.id.asc(),
            )
        )
        result = await self._session.execute(statement)
        return [
            self._to_entry(entry, user_id=owner_id)
            for entry, owner_id in result.all()
        ]

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _apply_filters(
        statement: Select,
        *,
        wallet_id: Optional[str],
        user_id: Optional[str],
        transaction_type: Optional[TransactionType],
        occurred_from: Optional[datetime],
        occurred_to: Optional[datetime],
    ) -> Select:
        """Narrows `statement` by each supplied filter, skipping those
        left as `None`."""
        if wallet_id is not None:
            statement = statement.where(
                TransactionLedgerModel.wallet_id == wallet_id
            )
        if user_id is not None:
            statement = statement.where(WalletModel.user_id == user_id)
        if transaction_type is not None:
            statement = statement.where(
                TransactionLedgerModel.transaction_type == transaction_type
            )
        if occurred_from is not None:
            statement = statement.where(
                TransactionLedgerModel.created_at >= occurred_from
            )
        if occurred_to is not None:
            statement = statement.where(
                TransactionLedgerModel.created_at <= occurred_to
            )
        return statement

    @staticmethod
    def _to_entry(
        entry: TransactionLedgerModel, *, user_id: str
    ) -> AuditLedgerEntry:
        """Maps a ledger row plus its wallet's owner to a plain
        [AuditLedgerEntry].

        Deposits and withdrawals written before the `direction` column
        existed are resolved from their type, which is unambiguous for
        those two. Legacy transfers are left as `None` — both legs
        share a type and a positive amount, so their direction is
        genuinely unrecoverable, and inventing one would put a
        fabricated number in an audit report.
        """
        direction = entry.direction
        if direction is None:
            if entry.transaction_type is TransactionType.DEPOSIT:
                direction = EntryDirection.CREDIT
            elif entry.transaction_type is TransactionType.WITHDRAWAL:
                direction = EntryDirection.DEBIT

        return AuditLedgerEntry(
            id=entry.id,
            wallet_id=entry.wallet_id,
            user_id=user_id,
            amount=entry.amount,
            transaction_type=entry.transaction_type,
            direction=direction,
            reference_id=entry.reference_id,
            counterparty_wallet_id=entry.counterparty_wallet_id,
            created_at=entry.created_at,
        )
