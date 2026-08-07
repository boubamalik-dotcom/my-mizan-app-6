"""Unit tests for the pure Layer 3 wallet business logic.

No FastAPI, no SQLAlchemy, no Pydantic, no database, no network —
every test here runs purely in memory, proving `wallet_service.py` and
`wallet_exceptions.py` are fully testable in isolation.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.layer_3_business.wallet.wallet_exceptions import (
    InsufficientFundsError,
    InvalidTransactionAmountError,
    WalletError,
    WalletLockedError,
)
from src.layer_3_business.wallet.wallet_service import WalletService


@pytest.fixture
def service() -> WalletService:
    return WalletService()


class TestExceptionHierarchy:
    def test_every_specific_exception_is_a_wallet_error(self) -> None:
        assert issubclass(InvalidTransactionAmountError, WalletError)
        assert issubclass(InsufficientFundsError, WalletError)
        assert issubclass(WalletLockedError, WalletError)

    def test_invalid_transaction_amount_error_carries_context(self) -> None:
        error = InvalidTransactionAmountError(Decimal("-5"), "must be greater than zero.")
        assert error.amount == Decimal("-5")
        assert "must be greater than zero" in str(error)

    def test_insufficient_funds_error_carries_context(self) -> None:
        error = InsufficientFundsError(Decimal("100"), Decimal("40"))
        assert error.requested_amount == Decimal("100")
        assert error.available_balance == Decimal("40")
        assert "100" in str(error) and "40" in str(error)

    def test_wallet_locked_error_carries_context(self) -> None:
        error = WalletLockedError("wallet-123")
        assert error.wallet_id == "wallet-123"
        assert "wallet-123" in str(error)


class TestValidateDepositAmount:
    def test_accepts_a_positive_decimal(self, service: WalletService) -> None:
        assert service.validate_deposit_amount(Decimal("10.50")) == Decimal("10.50")

    def test_rejects_zero(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_deposit_amount(Decimal("0"))

    def test_rejects_negative(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_deposit_amount(Decimal("-1"))

    def test_rejects_nan(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_deposit_amount(Decimal("NaN"))

    def test_rejects_infinity(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_deposit_amount(Decimal("Infinity"))

    def test_rejects_non_decimal_types(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_deposit_amount(10.5)  # type: ignore[arg-type]
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_deposit_amount("10.5")  # type: ignore[arg-type]
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_deposit_amount(10)  # type: ignore[arg-type]


class TestValidateWithdrawalAmount:
    def test_accepts_amount_within_balance(self, service: WalletService) -> None:
        assert service.validate_withdrawal_amount(
            Decimal("50"), current_balance=Decimal("100")
        ) == Decimal("50")

    def test_accepts_amount_exactly_equal_to_balance(self, service: WalletService) -> None:
        assert service.validate_withdrawal_amount(
            Decimal("100"), current_balance=Decimal("100")
        ) == Decimal("100")

    def test_rejects_amount_exceeding_balance(self, service: WalletService) -> None:
        with pytest.raises(InsufficientFundsError) as exc_info:
            service.validate_withdrawal_amount(Decimal("100.01"), current_balance=Decimal("100"))
        assert exc_info.value.requested_amount == Decimal("100.01")
        assert exc_info.value.available_balance == Decimal("100")

    def test_rejects_non_positive_amount_before_checking_balance(
        self, service: WalletService
    ) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_withdrawal_amount(Decimal("0"), current_balance=Decimal("100"))
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_withdrawal_amount(Decimal("-10"), current_balance=Decimal("100"))

    def test_rejects_withdrawal_from_zero_balance(self, service: WalletService) -> None:
        with pytest.raises(InsufficientFundsError):
            service.validate_withdrawal_amount(Decimal("0.01"), current_balance=Decimal("0"))


class TestValidateTransferAmount:
    def test_accepts_amount_within_sender_balance(self, service: WalletService) -> None:
        assert service.validate_transfer_amount(
            Decimal("25"), current_balance=Decimal("30")
        ) == Decimal("25")

    def test_rejects_amount_exceeding_sender_balance(self, service: WalletService) -> None:
        with pytest.raises(InsufficientFundsError):
            service.validate_transfer_amount(Decimal("31"), current_balance=Decimal("30"))

    def test_rejects_non_positive_amount(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.validate_transfer_amount(Decimal("0"), current_balance=Decimal("30"))


class TestEnsureWalletIsUnlocked:
    def test_does_not_raise_when_unlocked(self, service: WalletService) -> None:
        service.ensure_wallet_is_unlocked("wallet-1", is_locked=False)  # should not raise

    def test_raises_when_locked(self, service: WalletService) -> None:
        with pytest.raises(WalletLockedError) as exc_info:
            service.ensure_wallet_is_unlocked("wallet-1", is_locked=True)
        assert exc_info.value.wallet_id == "wallet-1"


class TestCalculateBalanceAfterDeposit:
    def test_adds_amount_to_balance(self, service: WalletService) -> None:
        new_balance = service.calculate_balance_after_deposit(
            current_balance=Decimal("100.00"), amount=Decimal("50.00")
        )
        assert new_balance == Decimal("150.00")

    def test_propagates_invalid_amount_error(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.calculate_balance_after_deposit(
                current_balance=Decimal("100"), amount=Decimal("-5")
            )


class TestCalculateBalanceAfterWithdrawal:
    def test_subtracts_amount_from_balance(self, service: WalletService) -> None:
        new_balance = service.calculate_balance_after_withdrawal(
            current_balance=Decimal("100.00"), amount=Decimal("40.00")
        )
        assert new_balance == Decimal("60.00")

    def test_never_produces_a_negative_balance(self, service: WalletService) -> None:
        with pytest.raises(InsufficientFundsError):
            service.calculate_balance_after_withdrawal(
                current_balance=Decimal("100"), amount=Decimal("150")
            )

    def test_withdrawing_full_balance_results_in_zero(self, service: WalletService) -> None:
        new_balance = service.calculate_balance_after_withdrawal(
            current_balance=Decimal("100.00"), amount=Decimal("100.00")
        )
        assert new_balance == Decimal("0.00")


class TestCalculateBalancesAfterTransfer:
    def test_moves_funds_between_balances(self, service: WalletService) -> None:
        new_sender, new_recipient = service.calculate_balances_after_transfer(
            sender_balance=Decimal("100.00"),
            recipient_balance=Decimal("20.00"),
            amount=Decimal("30.00"),
        )
        assert new_sender == Decimal("70.00")
        assert new_recipient == Decimal("50.00")

    def test_conserves_total_balance(self, service: WalletService) -> None:
        sender_balance = Decimal("100.00")
        recipient_balance = Decimal("20.00")
        total_before = sender_balance + recipient_balance

        new_sender, new_recipient = service.calculate_balances_after_transfer(
            sender_balance=sender_balance,
            recipient_balance=recipient_balance,
            amount=Decimal("30.00"),
        )

        assert new_sender + new_recipient == total_before

    def test_prevents_overdraft_on_sender(self, service: WalletService) -> None:
        with pytest.raises(InsufficientFundsError):
            service.calculate_balances_after_transfer(
                sender_balance=Decimal("100"),
                recipient_balance=Decimal("0"),
                amount=Decimal("150"),
            )

    def test_rejects_non_positive_transfer_amount(self, service: WalletService) -> None:
        with pytest.raises(InvalidTransactionAmountError):
            service.calculate_balances_after_transfer(
                sender_balance=Decimal("100"),
                recipient_balance=Decimal("0"),
                amount=Decimal("0"),
            )


class TestDecimalPrecision:
    """Guards against the exact class of bug `Decimal` exists to
    prevent: binary floating-point rounding error in repeated
    fractional arithmetic."""

    def test_repeated_fractional_deposits_stay_exact(self, service: WalletService) -> None:
        balance = Decimal("0.00")
        for _ in range(10):
            balance = service.calculate_balance_after_deposit(
                current_balance=balance, amount=Decimal("0.10")
            )
        # With `float`, `0.1 * 10` famously drifts from `1.0`
        # (`0.9999999999999999` or similar); `Decimal` must not.
        assert balance == Decimal("1.00")
