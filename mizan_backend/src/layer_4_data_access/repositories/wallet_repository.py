"""Layer 4 — async repository abstracting SQLAlchemy-based Digital
Wallet persistence.

This is where Layer 4 "properly abstracts Layer 5": `WalletRepository`
is the only place in the codebase, besides Layer 5 itself, that
imports `WalletModel`/`TransactionLedgerModel` or touches a SQLAlchemy
`AsyncSession`/`select()`. Layers 2 and 3 only ever see the plain
`WalletRecord`/`LedgerEntryRecord` dataclasses this module returns —
never a SQLAlchemy object — so a future swap of storage engine would
only ever require changes here, not in any calling code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from ...layer_5_storage.models.transaction_ledger_model import (
    TransactionLedgerModel,
    TransactionType,
)
from ...layer_5_storage.models.wallet_model import WalletModel


class WalletRepositoryError(Exception):
    """Base class for every error raised by `WalletRepository`."""


class WalletNotFoundError(WalletRepositoryError):
    """Raised when an operation references a wallet id that does not
    exist."""

    def __init__(self, wallet_id: str) -> None:
        """
        Args:
            wallet_id: The identifier that could not be resolved to an
                existing wallet.
        """
        self.wallet_id = wallet_id
        super().__init__(f'Wallet "{wallet_id}" does not exist.')


class WalletAlreadyExistsError(WalletRepositoryError):
    """Raised when `create_wallet` would violate the one-wallet-per-
    currency-per-user rule (`WalletModel`'s ``uq_wallet_user_currency``
    unique constraint)."""

    def __init__(self, user_id: str, currency: str) -> None:
        """
        Args:
            user_id: The user who already has a wallet in `currency`.
            currency: The currency code that collided.
        """
        self.user_id = user_id
        self.currency = currency
        super().__init__(
            f'User "{user_id}" already has a wallet in "{currency}".'
        )


class WalletConcurrencyConflictError(WalletRepositoryError):
    """Raised when `update_wallet_balance` detects that a wallet's row
    was modified by another transaction since it was read — i.e. the
    optimistic version check (`WalletModel`'s ``version_id_col``)
    failed.

    The correct response to this error is to re-fetch the wallet (via
    `get_wallet_by_id`), recompute the desired balance against its
    *current* state, and retry — never to blindly reapply the
    already-computed, now-stale balance.
    """

    def __init__(self, wallet_id: str) -> None:
        """
        Args:
            wallet_id: The identifier of the wallet whose update was
                rejected.
        """
        self.wallet_id = wallet_id
        super().__init__(
            f'Wallet "{wallet_id}" was modified concurrently by another '
            "transaction; this update was rejected. Re-read the wallet "
            "and retry."
        )


@dataclass(frozen=True, slots=True)
class WalletRecord:
    """An immutable snapshot of a wallet's persisted state, fully
    decoupled from the underlying `WalletModel` — callers never need
    to import (or even know about) SQLAlchemy."""

    id: str
    user_id: str
    currency: str
    balance: Decimal
    is_locked: bool
    version: int


@dataclass(frozen=True, slots=True)
class LedgerEntryRecord:
    """An immutable snapshot of a single, already-persisted ledger
    entry."""

    id: str
    wallet_id: str
    amount: Decimal
    transaction_type: TransactionType
    reference_id: Optional[str]
    counterparty_wallet_id: Optional[str]
    created_at: datetime


class WalletRepository:
    """Async repository for wallets and their append-only ledger.

    Bound to a single `AsyncSession` for its entire lifetime —
    typically one per `UnitOfWork` transaction (see
    `layer_4_data_access/uow/transaction_manager.py`) — so every
    read/write it performs participates in that one atomic
    transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: The `AsyncSession` this repository will use for
                every operation. Its transaction boundary (commit or
                rollback) is owned by the caller, not by this class.
        """
        self._session = session

    async def create_wallet(self, *, user_id: str, currency: str) -> WalletRecord:
        """Creates and persists a new, zero-balance, unlocked wallet
        linked to `user_id`.

        Args:
            user_id: The id of the registered user (`UserModel.id`)
                this wallet belongs to. Enforced as a real foreign key
                by `WalletModel` — creating a wallet for a `user_id`
                that does not exist raises `IntegrityError`.
            currency: The three-letter currency code this wallet is
                denominated in.

        Returns:
            A `WalletRecord` snapshot of the newly created wallet.

        Raises:
            WalletAlreadyExistsError: If `user_id` already has a
                wallet in `currency` (enforced by
                ``uq_wallet_user_currency``).
        """
        wallet = WalletModel(user_id=user_id, currency=currency)
        self._session.add(wallet)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise WalletAlreadyExistsError(user_id, currency) from exc
        return self._to_record(wallet)

    async def get_wallet_by_id(self, wallet_id: str) -> Optional[WalletRecord]:
        """Fetches a wallet by its id.

        Args:
            wallet_id: The wallet's identifier.

        Returns:
            A `WalletRecord` snapshot, or `None` if no wallet exists
            with that id.
        """
        wallet = await self._session.get(WalletModel, wallet_id)
        return self._to_record(wallet) if wallet is not None else None

    async def update_wallet_balance(
        self,
        wallet_id: str,
        new_balance: Decimal,
        *,
        expected_version: int,
    ) -> WalletRecord:
        """Securely updates a wallet's balance using optimistic
        concurrency control.

        `expected_version` must be the `version` value from the
        `WalletRecord` this new balance was computed against (i.e.
        from an earlier `get_wallet_by_id` call). Two independent
        safeguards then apply:

        1. If the wallet's *currently stored* version no longer
           matches `expected_version`, the conflict is detected
           immediately and `WalletConcurrencyConflictError` is raised
           before any write is attempted.
        2. Otherwise, the `UPDATE` SQLAlchemy issues for this flush
           still includes ``WHERE version = :expected_version`` (via
           `WalletModel`'s ``version_id_col``) — closing the residual
           race where another transaction commits a change in the
           brief window between this method's read and its write.
           `sqlalchemy.orm.exc.StaleDataError` from that path is
           likewise translated into `WalletConcurrencyConflictError`.

        Args:
            wallet_id: The wallet to update.
            new_balance: The balance to persist (already computed by
                Layer 3 — this method does not re-derive it).
            expected_version: The version the caller last observed for
                this wallet.

        Returns:
            A `WalletRecord` snapshot reflecting the new balance and
            incremented version.

        Raises:
            WalletNotFoundError: If `wallet_id` does not exist.
            WalletConcurrencyConflictError: If the wallet was modified
                concurrently since `expected_version` was read.
        """
        wallet = await self._session.get(WalletModel, wallet_id)
        if wallet is None:
            raise WalletNotFoundError(wallet_id)
        if wallet.version != expected_version:
            raise WalletConcurrencyConflictError(wallet_id)

        wallet.balance = new_balance
        try:
            await self._session.flush()
        except StaleDataError as exc:
            raise WalletConcurrencyConflictError(wallet_id) from exc

        return self._to_record(wallet)

    async def set_wallet_locked(self, wallet_id: str, *, is_locked: bool) -> WalletRecord:
        """Sets a wallet's locked/unlocked status (e.g. to freeze it
        for a compliance review).

        Args:
            wallet_id: The wallet to update.
            is_locked: The new locked status.

        Returns:
            A `WalletRecord` snapshot reflecting the new status.

        Raises:
            WalletNotFoundError: If `wallet_id` does not exist.
        """
        wallet = await self._session.get(WalletModel, wallet_id)
        if wallet is None:
            raise WalletNotFoundError(wallet_id)

        wallet.is_locked = is_locked
        await self._session.flush()
        return self._to_record(wallet)

    async def append_ledger_entry(
        self,
        *,
        wallet_id: str,
        amount: Decimal,
        transaction_type: TransactionType,
        reference_id: Optional[str] = None,
        counterparty_wallet_id: Optional[str] = None,
    ) -> LedgerEntryRecord:
        """Durably appends one immutable row to the transaction
        ledger.

        Args:
            wallet_id: The wallet this entry belongs to.
            amount: The transaction's positive magnitude.
            transaction_type: What kind of event this entry records.
            reference_id: Optional correlation id — for a transfer,
                the same `reference_id` should be passed for both the
                sending and receiving wallet's entries.
            counterparty_wallet_id: For a transfer, the wallet on the
                other side of it; `None` for deposits/withdrawals.

        Returns:
            A `LedgerEntryRecord` snapshot of the newly persisted
            entry.

        Raises:
            WalletNotFoundError: If `wallet_id` does not reference an
                existing wallet (surfaced as a foreign-key violation).
        """
        entry = TransactionLedgerModel(
            wallet_id=wallet_id,
            amount=amount,
            transaction_type=transaction_type,
            reference_id=reference_id,
            counterparty_wallet_id=counterparty_wallet_id,
        )
        self._session.add(entry)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise WalletNotFoundError(wallet_id) from exc

        return self._to_ledger_record(entry)

    # -- Internal mapping helpers ---------------------------------------

    @staticmethod
    def _to_record(wallet: WalletModel) -> WalletRecord:
        """Maps a `WalletModel` row to its plain-data `WalletRecord`
        counterpart."""
        return WalletRecord(
            id=wallet.id,
            user_id=wallet.user_id,
            currency=wallet.currency,
            balance=wallet.balance,
            is_locked=wallet.is_locked,
            version=wallet.version,
        )

    @staticmethod
    def _to_ledger_record(entry: TransactionLedgerModel) -> LedgerEntryRecord:
        """Maps a `TransactionLedgerModel` row to its plain-data
        `LedgerEntryRecord` counterpart."""
        return LedgerEntryRecord(
            id=entry.id,
            wallet_id=entry.wallet_id,
            amount=entry.amount,
            transaction_type=entry.transaction_type,
            reference_id=entry.reference_id,
            counterparty_wallet_id=entry.counterparty_wallet_id,
            created_at=entry.created_at,
        )
