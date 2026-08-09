"""Layer 2 — Digital Wallet controller.

`WalletController` orchestrates the Digital Wallet's use cases:

1. Enforces ownership: every method that names a wallet id fetches it
   and immediately checks that it belongs to the authenticated caller
   (`wallet.user_id == current_user_id`), raising `HTTPException(403)`
   *before* any further database query — validation, balance
   computation, or write — is attempted for that wallet. A transfer's
   destination wallet is deliberately exempt (see `transfer` below):
   sending money *to* someone else's wallet is the entire point of a
   transfer.
2. Calls Layer 3 (`WalletService`) to validate amounts and business
   rules — pure logic, no I/O — before any database write is
   attempted.
3. Uses Layer 4 (`UnitOfWork`, `WalletRepository`) to execute the
   actual balance update and ledger append together, atomically,
   inside a single Unit of Work.
4. Catches every domain exception raised by Layers 3/4
   (`wallet_exceptions.py` and `wallet_repository.py`) and translates
   it into the appropriate FastAPI `HTTPException`, so this is the
   *only* place in the backend where a wallet domain error becomes an
   HTTP status code.

`wallet_routes.py` stays a thin adapter over this class: it never
contains business logic, ownership checks, or exception-translation
logic itself, only request/response marshalling.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from decimal import Decimal
from typing import Callable, Iterator, Optional, Tuple

from fastapi import HTTPException, status

from ...layer_3_business.wallet.wallet_exceptions import (
    InsufficientFundsError,
    InvalidTransactionAmountError,
    WalletLockedError,
)
from ...layer_3_business.wallet.wallet_service import WalletService
from ...layer_4_data_access.repositories.wallet_repository import (
    EntryDirection,
    TransactionType,
    WalletAlreadyExistsError,
    WalletConcurrencyConflictError,
    WalletNotFoundError,
    WalletRecord,
)
from ...layer_4_data_access.uow.transaction_manager import UnitOfWork


class WalletController:
    """Coordinates Layer 3 business rules and Layer 4 transactional
    persistence to serve the Digital Wallet's REST endpoints."""

    def __init__(
        self,
        *,
        wallet_service: WalletService,
        unit_of_work_factory: Callable[[], UnitOfWork] = UnitOfWork,
    ) -> None:
        """
        Args:
            wallet_service: The Layer 3 service used to validate
                amounts and compute new balances.
            unit_of_work_factory: A zero-argument callable returning a
                fresh, not-yet-entered `UnitOfWork` each time it is
                invoked. Defaults to the `UnitOfWork` class itself
                (a class is a valid factory for its own instances).
                Injected so tests can point every unit of work this
                controller opens at an isolated test database.
        """
        self._wallet_service = wallet_service
        self._unit_of_work_factory = unit_of_work_factory

    # -- Creation -------------------------------------------------------

    async def create_wallet(
        self, *, currency: str, current_user_id: str
    ) -> WalletRecord:
        """Creates a new, zero-balance, unlocked wallet owned by the
        authenticated caller.

        No ownership check is needed here — unlike every other
        method on this class, there is no pre-existing wallet to own
        yet; `current_user_id` is simply who the new wallet is
        created *for*.

        Args:
            currency: The three-letter currency code for the new
                wallet.
            current_user_id: The id of the authenticated caller, who
                will own the new wallet.

        Returns:
            The newly created wallet's `WalletRecord` (balance `0`).

        Raises:
            HTTPException: 409 if the caller already has a wallet in
                `currency`.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                wallet = await uow.wallets.create_wallet(
                    user_id=current_user_id, currency=currency
                )
                await uow.commit()

        return wallet

    # -- Read ---------------------------------------------------------------

    async def get_my_wallet(self, *, current_user_id: str) -> WalletRecord:
        """Fetches the authenticated caller's own wallet, for
        `GET /wallet` — the lookup a client uses on app start-up to
        find its wallet without already knowing a `wallet_id` (see
        `mizan_frontend`'s `WalletRepository.getOrCreateWallet`, which
        calls this first and only falls back to `POST /wallet` on a
        **404**).

        No ownership check is needed here (unlike `get_balance`,
        which is keyed by an arbitrary `wallet_id` that could belong
        to anyone): the wallet is looked up *by* `current_user_id` in
        the first place, so whatever is returned is, by construction,
        already the caller's own.

        Args:
            current_user_id: The id of the authenticated caller.

        Returns:
            The caller's `WalletRecord`.

        Raises:
            HTTPException: 404 if the caller has not provisioned a
                wallet yet.
        """
        async with self._unit_of_work_factory() as uow:
            wallet = await uow.wallets.get_wallet_by_user_id(current_user_id)

        if wallet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
            )
        return wallet

    async def get_balance(self, wallet_id: str, *, current_user_id: str) -> WalletRecord:
        """Fetches a wallet's current balance and status.

        Args:
            wallet_id: The wallet to fetch.
            current_user_id: The id of the authenticated caller, as
                resolved by `layer_2_api.auth.deps.get_current_user`.

        Returns:
            The wallet's current `WalletRecord`.

        Raises:
            HTTPException: 404 if `wallet_id` does not exist, or 403
                if it does not belong to `current_user_id`.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                wallet = self._require_wallet(
                    await uow.wallets.get_wallet_by_id(wallet_id), wallet_id
                )
                self._require_ownership(wallet, current_user_id)
        return wallet

    # -- Deposits & withdrawals -------------------------------------------

    async def deposit(
        self, *, wallet_id: str, amount: Decimal, current_user_id: str
    ) -> WalletRecord:
        """Credits `wallet_id` by `amount`.

        Validates the amount via Layer 3 *before* opening any database
        transaction — an obviously-invalid amount (zero, negative, not
        a finite `Decimal`) is rejected without ever touching the
        database. Ownership is checked immediately after the wallet is
        fetched, before the balance update or ledger append (the
        actual writes) are attempted.

        Args:
            wallet_id: The wallet to credit.
            amount: The amount to deposit.
            current_user_id: The id of the authenticated caller.

        Returns:
            The wallet's `WalletRecord` after the deposit.

        Raises:
            HTTPException: 422 for an invalid amount, 404 if
                `wallet_id` does not exist, 403 if it does not belong
                to `current_user_id`, 423 if the wallet is locked, or
                409 on a concurrency conflict.
        """
        with self._translate_domain_errors():
            self._wallet_service.validate_deposit_amount(amount)

        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                wallet = self._require_wallet(
                    await uow.wallets.get_wallet_by_id(wallet_id), wallet_id
                )
                self._require_ownership(wallet, current_user_id)
                self._wallet_service.ensure_wallet_is_unlocked(
                    wallet.id, wallet.is_locked
                )
                new_balance = self._wallet_service.calculate_balance_after_deposit(
                    wallet.balance, amount
                )

                updated = await uow.wallets.update_wallet_balance(
                    wallet.id, new_balance, expected_version=wallet.version
                )
                await uow.wallets.append_ledger_entry(
                    wallet_id=wallet.id,
                    amount=amount,
                    transaction_type=TransactionType.DEPOSIT,
                    direction=EntryDirection.CREDIT,
                )
                await uow.commit()

        return updated

    async def withdraw(
        self, *, wallet_id: str, amount: Decimal, current_user_id: str
    ) -> WalletRecord:
        """Debits `wallet_id` by `amount`.

        Unlike `deposit`, the amount alone cannot be validated before
        opening a transaction — checking for sufficient funds requires
        first reading the wallet's current balance via Layer 4.
        Ownership is checked immediately after that same read, still
        strictly *before* the amount validation, balance update, or
        ledger append are attempted.

        Args:
            wallet_id: The wallet to debit.
            amount: The amount to withdraw.
            current_user_id: The id of the authenticated caller.

        Returns:
            The wallet's `WalletRecord` after the withdrawal.

        Raises:
            HTTPException: 422 for an invalid amount, 400 for
                insufficient funds, 404 if `wallet_id` does not exist,
                403 if it does not belong to `current_user_id`, 423 if
                the wallet is locked, or 409 on a concurrency conflict.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                wallet = self._require_wallet(
                    await uow.wallets.get_wallet_by_id(wallet_id), wallet_id
                )
                self._require_ownership(wallet, current_user_id)
                self._wallet_service.ensure_wallet_is_unlocked(
                    wallet.id, wallet.is_locked
                )
                new_balance = self._wallet_service.calculate_balance_after_withdrawal(
                    wallet.balance, amount
                )

                updated = await uow.wallets.update_wallet_balance(
                    wallet.id, new_balance, expected_version=wallet.version
                )
                await uow.wallets.append_ledger_entry(
                    wallet_id=wallet.id,
                    amount=amount,
                    transaction_type=TransactionType.WITHDRAWAL,
                    direction=EntryDirection.DEBIT,
                )
                await uow.commit()

        return updated

    # -- Transfers ----------------------------------------------------------

    async def transfer(
        self,
        *,
        source_wallet_id: str,
        destination_wallet_id: str,
        amount: Decimal,
        current_user_id: str,
    ) -> Tuple[WalletRecord, WalletRecord]:
        """Moves `amount` from `source_wallet_id` to
        `destination_wallet_id`.

        Ownership is only enforced on the *source* wallet — the
        authenticated caller must own the wallet funds leave, but
        sending money *to* another user's wallet is the entire point
        of a transfer, so the destination wallet is deliberately
        exempt from the ownership check. Both wallets are still
        validated for existence and lock status, and the transfer
        amount is checked against the source's balance via Layer 3,
        all before either wallet's balance is written.

        Args:
            source_wallet_id: The wallet the funds leave.
            destination_wallet_id: The wallet the funds arrive at.
            amount: The amount to transfer.
            current_user_id: The id of the authenticated caller, who
                must own `source_wallet_id`.

        Returns:
            A `(updated_source, updated_destination)` tuple.

        Raises:
            HTTPException: 422 for an invalid amount, 400 for
                insufficient funds, 404 if either wallet does not
                exist, 403 if the caller does not own the source
                wallet, 423 if either wallet is locked, or 409 on a
                concurrency conflict.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                source = self._require_wallet(
                    await uow.wallets.get_wallet_by_id(source_wallet_id),
                    source_wallet_id,
                )
                self._require_ownership(source, current_user_id)
                destination = self._require_wallet(
                    await uow.wallets.get_wallet_by_id(destination_wallet_id),
                    destination_wallet_id,
                )
                self._wallet_service.ensure_wallet_is_unlocked(
                    source.id, source.is_locked
                )
                self._wallet_service.ensure_wallet_is_unlocked(
                    destination.id, destination.is_locked
                )

                new_source_balance, new_destination_balance = (
                    self._wallet_service.calculate_balances_after_transfer(
                        source.balance, destination.balance, amount
                    )
                )

                # Updating in a fixed, deterministic order (ascending
                # id) — rather than always "source first" — is what
                # prevents a lock-ordering deadlock when two transfers
                # between the same pair of wallets race in opposite
                # directions at the database level.
                first_id, second_id = sorted([source.id, destination.id])
                if first_id == source.id:
                    first_balance, first_version = new_source_balance, source.version
                    second_balance, second_version = (
                        new_destination_balance,
                        destination.version,
                    )
                else:
                    first_balance, first_version = (
                        new_destination_balance,
                        destination.version,
                    )
                    second_balance, second_version = (
                        new_source_balance,
                        source.version,
                    )

                await uow.wallets.update_wallet_balance(
                    first_id, first_balance, expected_version=first_version
                )
                await uow.wallets.update_wallet_balance(
                    second_id, second_balance, expected_version=second_version
                )

                reference_id = uuid.uuid4().hex
                # The two legs are distinguished only by `direction`:
                # they share a type, a positive amount, and a reference.
                await uow.wallets.append_ledger_entry(
                    wallet_id=source.id,
                    amount=amount,
                    transaction_type=TransactionType.TRANSFER,
                    direction=EntryDirection.DEBIT,
                    reference_id=reference_id,
                    counterparty_wallet_id=destination.id,
                )
                await uow.wallets.append_ledger_entry(
                    wallet_id=destination.id,
                    amount=amount,
                    transaction_type=TransactionType.TRANSFER,
                    direction=EntryDirection.CREDIT,
                    reference_id=reference_id,
                    counterparty_wallet_id=source.id,
                )
                await uow.commit()

                updated_source = await uow.wallets.get_wallet_by_id(source.id)
                updated_destination = await uow.wallets.get_wallet_by_id(
                    destination.id
                )

        assert updated_source is not None and updated_destination is not None
        return updated_source, updated_destination

    # -- Internal helpers -------------------------------------------------

    @staticmethod
    def _require_wallet(
        wallet: Optional[WalletRecord], wallet_id: str
    ) -> WalletRecord:
        """Raises `WalletNotFoundError` if `wallet` is `None`,
        otherwise returns it unchanged — a small helper so the
        "fetch, then 404 if missing" pattern is not repeated manually
        in every method above."""
        if wallet is None:
            raise WalletNotFoundError(wallet_id)
        return wallet

    @staticmethod
    def _require_ownership(wallet: WalletRecord, current_user_id: str) -> None:
        """Raises `HTTPException(403)` unless `wallet` belongs to
        `current_user_id` — the sole ownership gate every
        wallet-reading or wallet-mutating operation passes through.

        Deliberately raises `HTTPException` directly rather than a
        Layer 3/4 domain exception translated by
        `_translate_domain_errors`: ownership is an authorization
        concern that belongs entirely to Layer 2, not a business rule
        Layers 3/4 have any opinion about.
        """
        if wallet.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

    @staticmethod
    @contextmanager
    def _translate_domain_errors() -> Iterator[None]:
        """Context manager translating every domain exception Layers
        3/4 can raise into the matching `HTTPException`, so each
        public method above needs only one `with` statement instead
        of repeating this mapping.

        Mapping:

        * `InvalidTransactionAmountError` -> 422 Unprocessable Entity
        * `InsufficientFundsError` -> 400 Bad Request
        * `WalletLockedError` -> 423 Locked
        * `WalletNotFoundError` -> 404 Not Found
        * `WalletConcurrencyConflictError` -> 409 Conflict
        * `WalletAlreadyExistsError` -> 409 Conflict
        """
        try:
            yield
        except InvalidTransactionAmountError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except InsufficientFundsError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except WalletLockedError as exc:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED, detail=str(exc)
            ) from exc
        except WalletNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except WalletConcurrencyConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{exc} Please retry the request.",
            ) from exc
        except WalletAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
