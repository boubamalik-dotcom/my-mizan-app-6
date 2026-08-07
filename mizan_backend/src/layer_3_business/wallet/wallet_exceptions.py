"""Domain-level exceptions for the Digital Wallet's business logic
(Layer 3).

STRICT RULE: this module has zero dependencies on FastAPI,
SQLAlchemy, Pydantic, or any other framework/infrastructure package —
every exception here is plain Python, so it can be raised, caught, and
unit-tested without importing anything beyond the standard library.
Layer 2 (`wallet_controller.py`) is responsible for translating these
into the appropriate HTTP status code; Layer 3 itself never knows
about HTTP.
"""
from __future__ import annotations

from decimal import Decimal


class WalletError(Exception):
    """Base class for every error raised by the Digital Wallet's
    business logic.

    Catching `WalletError` at a call site (e.g. in a Layer 2
    controller) is guaranteed to catch every domain-specific wallet
    exception below, without needing to know the full list of
    subclasses in advance.
    """


class InvalidTransactionAmountError(WalletError):
    """Raised when a deposit, withdrawal, or transfer amount fails
    validation — for example, an amount that is zero, negative, not a
    finite number, or otherwise not a legitimate monetary value.

    Every transaction amount in this system must be strictly positive:
    direction (deposit vs. withdrawal vs. transfer) is conveyed by
    *which operation* is invoked, never by the sign of the amount
    itself.
    """

    def __init__(self, amount: Decimal, reason: str) -> None:
        """
        Args:
            amount: The invalid amount that was supplied.
            reason: A short, human-readable explanation of why
                `amount` was rejected (e.g. "must be greater than
                zero").
        """
        self.amount = amount
        self.reason = reason
        super().__init__(f"Invalid transaction amount {amount!r}: {reason}")


class InsufficientFundsError(WalletError):
    """Raised when a withdrawal or transfer would overdraw a wallet's
    available balance.

    This is the primary guard against overdrafts: every debiting
    operation must pass through `WalletService`, which raises this
    *before* returning a computed result, so a caller can never derive
    a negative balance from this layer.
    """

    def __init__(self, requested_amount: Decimal, available_balance: Decimal) -> None:
        """
        Args:
            requested_amount: The amount that was requested to be
                withdrawn or transferred.
            available_balance: The balance actually available to cover
                it.
        """
        self.requested_amount = requested_amount
        self.available_balance = available_balance
        super().__init__(
            "Insufficient funds: requested "
            f"{requested_amount!r}, but only {available_balance!r} is available."
        )


class WalletLockedError(WalletError):
    """Raised when an operation is attempted against a wallet that is
    currently locked (e.g. frozen for a compliance review, or closed)
    and therefore not eligible for deposits, withdrawals, or
    transfers.
    """

    def __init__(self, wallet_id: str) -> None:
        """
        Args:
            wallet_id: The identifier of the locked wallet.
        """
        self.wallet_id = wallet_id
        super().__init__(f'Wallet "{wallet_id}" is locked and cannot be transacted on.')
