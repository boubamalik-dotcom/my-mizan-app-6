"""Layer 3 — pure business logic for the Digital Wallet.

STRICT RULE: this module has zero dependencies on FastAPI,
SQLAlchemy, Pydantic, or any other framework/infrastructure package.
It operates exclusively on `decimal.Decimal` and plain Python types —
never `float`, which cannot exactly represent most decimal fractions
(e.g. `0.1 + 0.2 != 0.3` in binary floating point) and is therefore
never acceptable for monetary arithmetic — so it can be unit tested in
complete isolation and reused unchanged behind any transport or
storage engine.

Callers (Layer 2, via Layer 4) are responsible for fetching a wallet's
current balance/lock status beforehand and persisting the computed
result afterwards, inside a single atomic transaction; this module
never performs any I/O itself.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Tuple

from .wallet_exceptions import (
    InsufficientFundsError,
    InvalidTransactionAmountError,
    WalletLockedError,
)

#: The smallest transaction amount this service will accept —
#: strictly greater than zero, since every transaction amount is a
#: positive magnitude (direction is conveyed by which operation is
#: invoked, never by the sign of the amount itself).
ZERO: Decimal = Decimal("0")


class WalletService:
    """Encapsulates the pure mathematical and logical rules governing
    a Digital Wallet's balance: amount validation, overdraft
    prevention, and balance arithmetic for deposits, withdrawals, and
    transfers.

    Every method here is a deterministic, side-effect-free function of
    its arguments: no database access, no network calls, and no
    mutation of any state outside of what it returns.
    """

    # -- Deposit validation -------------------------------------------------

    def validate_deposit_amount(self, amount: Decimal) -> Decimal:
        """Validates that `amount` is a legitimate deposit amount.

        Args:
            amount: The proposed deposit amount.

        Returns:
            `amount`, unchanged, if it is valid.

        Raises:
            InvalidTransactionAmountError: If `amount` is not a
                `Decimal`, is not finite, or is not strictly greater
                than zero.
        """
        return self._validate_positive_amount(amount)

    # -- Withdrawal & transfer validation ------------------------------------

    def validate_withdrawal_amount(
        self, amount: Decimal, current_balance: Decimal
    ) -> Decimal:
        """Validates that `amount` is a legitimate withdrawal amount
        given `current_balance`.

        Args:
            amount: The proposed withdrawal amount.
            current_balance: The wallet's balance before the
                withdrawal.

        Returns:
            `amount`, unchanged, if it is valid.

        Raises:
            InvalidTransactionAmountError: If `amount` is not a
                `Decimal`, is not finite, or is not strictly greater
                than zero.
            InsufficientFundsError: If `amount` exceeds
                `current_balance` — the primary overdraft guard.
        """
        validated_amount = self._validate_positive_amount(amount)
        self._validate_sufficient_balance(validated_amount, current_balance)
        return validated_amount

    def validate_transfer_amount(
        self, amount: Decimal, current_balance: Decimal
    ) -> Decimal:
        """Validates that `amount` is a legitimate *outgoing* transfer
        amount, given the sending wallet's `current_balance`.

        From the sender's perspective, an outgoing transfer is
        governed by exactly the same overdraft rule as a withdrawal —
        this method is exposed separately from
        `validate_withdrawal_amount` so calling code can express its
        intent clearly, and so a future divergence between the two
        rules (e.g. a transfer-specific fee or limit) only ever needs
        to change in one place.

        Args:
            amount: The proposed transfer amount.
            current_balance: The sending wallet's balance before the
                transfer.

        Returns:
            `amount`, unchanged, if it is valid.

        Raises:
            InvalidTransactionAmountError: If `amount` is not a
                `Decimal`, is not finite, or is not strictly greater
                than zero.
            InsufficientFundsError: If `amount` exceeds
                `current_balance`.
        """
        validated_amount = self._validate_positive_amount(amount)
        self._validate_sufficient_balance(validated_amount, current_balance)
        return validated_amount

    # -- Wallet-status guard --------------------------------------------

    def ensure_wallet_is_unlocked(self, wallet_id: str, is_locked: bool) -> None:
        """Guards an operation against being applied to a locked
        wallet (e.g. frozen for a compliance review, or closed).

        Args:
            wallet_id: The identifier of the wallet being checked —
                used only to build a clear error message.
            is_locked: Whether the wallet is currently locked, as
                determined by the caller (Layer 2, from data fetched
                via Layer 4).

        Raises:
            WalletLockedError: If `is_locked` is `True`.
        """
        if is_locked:
            raise WalletLockedError(wallet_id)

    # -- Balance arithmetic ----------------------------------------------

    def calculate_balance_after_deposit(
        self, current_balance: Decimal, amount: Decimal
    ) -> Decimal:
        """Computes a wallet's new balance after depositing `amount`.

        Args:
            current_balance: The balance before the deposit.
            amount: The amount to deposit.

        Returns:
            `current_balance + amount`.

        Raises:
            InvalidTransactionAmountError: See `validate_deposit_amount`.
        """
        validated_amount = self.validate_deposit_amount(amount)
        return current_balance + validated_amount

    def calculate_balance_after_withdrawal(
        self, current_balance: Decimal, amount: Decimal
    ) -> Decimal:
        """Computes a wallet's new balance after withdrawing `amount`.

        Args:
            current_balance: The balance before the withdrawal.
            amount: The amount to withdraw.

        Returns:
            `current_balance - amount`.

        Raises:
            InvalidTransactionAmountError: See
                `validate_withdrawal_amount`.
            InsufficientFundsError: If `amount` exceeds
                `current_balance`.
        """
        validated_amount = self.validate_withdrawal_amount(amount, current_balance)
        return current_balance - validated_amount

    def calculate_balances_after_transfer(
        self,
        sender_balance: Decimal,
        recipient_balance: Decimal,
        amount: Decimal,
    ) -> Tuple[Decimal, Decimal]:
        """Computes both wallets' new balances after transferring
        `amount` from the sender to the recipient.

        Args:
            sender_balance: The sending wallet's balance before the
                transfer.
            recipient_balance: The receiving wallet's balance before
                the transfer.
            amount: The amount to transfer.

        Returns:
            A `(new_sender_balance, new_recipient_balance)` tuple. The
            total of the two balances is always conserved: nothing is
            created or destroyed by a transfer.

        Raises:
            InvalidTransactionAmountError: See
                `validate_transfer_amount`.
            InsufficientFundsError: If `amount` exceeds
                `sender_balance`.
        """
        validated_amount = self.validate_transfer_amount(amount, sender_balance)
        new_sender_balance = sender_balance - validated_amount
        new_recipient_balance = recipient_balance + validated_amount
        return new_sender_balance, new_recipient_balance

    # -- Internal validation helpers ----------------------------------------

    def _validate_positive_amount(self, amount: Decimal) -> Decimal:
        """Raises `InvalidTransactionAmountError` unless `amount` is a
        finite, strictly positive `Decimal`; otherwise returns it
        unchanged."""
        if not isinstance(amount, Decimal):
            raise InvalidTransactionAmountError(
                amount,
                f"must be a decimal.Decimal instance, got {type(amount).__name__}.",
            )

        try:
            is_finite = amount.is_finite()
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise InvalidTransactionAmountError(amount, "is not a valid number.") from exc

        if not is_finite:
            raise InvalidTransactionAmountError(
                amount, "must be a finite number (not NaN or Infinity)."
            )
        if amount <= ZERO:
            raise InvalidTransactionAmountError(amount, "must be greater than zero.")

        return amount

    def _validate_sufficient_balance(
        self, amount: Decimal, current_balance: Decimal
    ) -> None:
        """Raises `InsufficientFundsError` if `amount` exceeds
        `current_balance`."""
        if amount > current_balance:
            raise InsufficientFundsError(amount, current_balance)
