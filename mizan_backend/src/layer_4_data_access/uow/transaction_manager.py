"""Layer 4 — asynchronous Unit of Work shared by every feature that
needs an atomic database transaction (the Digital Wallet and
Authentication, so far).

Guarantees ACID transaction boundaries around one or more repository
operations: e.g. a wallet's balance update and its corresponding
ledger entry, or a new user account and whatever else a future
registration flow needs to persist alongside it, are always committed
together, or not at all.
"""
from __future__ import annotations

import logging
from types import TracebackType
from typing import Optional, Type

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...layer_5_storage.db_config import async_session_factory
from ..repositories.user_repository import UserRepository
from ..repositories.wallet_repository import WalletRepository

logger = logging.getLogger(__name__)


class UnitOfWork:
    """A single atomic transaction boundary around one or more
    repository operations.

    Used as an async context manager::

        async with UnitOfWork() as uow:
            wallet = await uow.wallets.get_wallet_by_id(wallet_id)
            new_balance = wallet_service.calculate_balance_after_deposit(
                wallet.balance, amount
            )
            await uow.wallets.update_wallet_balance(
                wallet_id, new_balance, expected_version=wallet.version
            )
            await uow.wallets.append_ledger_entry(
                wallet_id=wallet_id,
                amount=amount,
                transaction_type=TransactionType.DEPOSIT,
            )
            await uow.commit()

    Or, for authentication::

        async with UnitOfWork() as uow:
            user = await uow.users.create_user(
                email=email, hashed_password=hashed_password, full_name=full_name
            )
            await uow.commit()

    Because `self.users` and `self.wallets` share the same session,
    creating a wallet for a just-created (or already-existing) user is
    itself a single atomic operation spanning both repositories::

        async with UnitOfWork() as uow:
            user = await uow.users.get_user_by_email(email)
            wallet = await uow.wallets.create_wallet(
                user_id=user.id, currency="USD"
            )
            await uow.commit()

    `WalletModel.user_id` is a real foreign key into `users.id`, so
    attempting this with a `user_id` that does not correspond to an
    existing row fails loudly (`IntegrityError`) rather than silently
    creating an orphaned wallet.

    If the ``async with`` block exits because of an unhandled
    exception, `__aexit__` rolls the transaction back automatically —
    so a failure partway through (e.g. `append_ledger_entry` raising
    after `update_wallet_balance` already flushed its change *within
    the same, not-yet-committed transaction*) leaves the database
    exactly as it was before the block started; nothing partially
    applied is ever visible to another transaction, satisfying
    atomicity and isolation together.

    Every `UnitOfWork` opens its **own** `AsyncSession` — and therefore
    its own database transaction and, on a real database, its own
    connection — so two `UnitOfWork`s used concurrently (e.g. two
    simultaneous deposit requests) never share transactional state
    with each other; each is independently atomic, and it is
    `WalletModel`'s optimistic version check that reconciles them if
    they touch the same wallet.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    ) -> None:
        """
        Args:
            session_factory: Used to open this unit of work's session
                on `__aenter__`. Defaults to the process-wide factory
                configured in `layer_5_storage/db_config.py`; tests
                should pass one bound to an isolated test database
                instead.
        """
        self._session_factory = session_factory
        self._session: Optional[AsyncSession] = None
        self.wallets: Optional[WalletRepository] = None
        self.users: Optional[UserRepository] = None

    async def __aenter__(self) -> "UnitOfWork":
        """Opens a new session/transaction and binds every repository
        (`self.wallets`, `self.users`) to it."""
        self._session = self._session_factory()
        self.wallets = WalletRepository(self._session)
        self.users = UserRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Rolls back automatically if the ``async with`` block raised,
        then always closes the session — releasing its connection back
        to the pool — regardless of outcome.

        Deliberately does **not** auto-commit on a clean exit —
        callers must call `commit()` explicitly, so that forgetting to
        commit fails safe (nothing is persisted) rather than silently
        succeeding.
        """
        try:
            if exc_type is not None:
                await self.rollback()
        finally:
            if self._session is not None:
                await self._session.close()
                self._session = None
                self.wallets = None
                self.users = None

    async def commit(self) -> None:
        """Durably commits every change made through this unit of
        work's repositories (`self.wallets`, `self.users`). Must be
        called explicitly on every success path.

        Raises:
            RuntimeError: If called outside of an active transaction
                (i.e. before `__aenter__` or after `__aexit__`).
        """
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork.commit() called outside of an active "
                "transaction — use 'async with UnitOfWork() as uow:' first."
            )
        await self._session.commit()

    async def rollback(self) -> None:
        """Discards every change made through this unit of work's
        repositories during this transaction. Invoked automatically by
        `__aexit__` when the ``async with`` block raises, but may also
        be called explicitly (e.g. after detecting a business-rule
        violation that should abort the transaction without raising).
        Safe to call even if no session is currently open."""
        if self._session is None:
            return
        await self._session.rollback()
