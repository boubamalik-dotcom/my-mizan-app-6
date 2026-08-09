"""Unit tests for the pure Layer 3 audit rules.

No FastAPI, no SQLAlchemy, no Pydantic, no database — every test runs
in memory, proving `audit_service.py` is fully testable in isolation.

Reconciliation is the one thing a compliance feature cannot afford to
get subtly wrong, so these cover the awkward cases (transfers, unknown
directions, fractional amounts) at least as heavily as the happy path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.layer_3_business.audit.audit_exceptions import (
    AuditError,
    InvalidAuditQueryError,
)
from src.layer_3_business.audit.audit_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    AuditableEntry,
    AuditService,
)


@pytest.fixture
def service() -> AuditService:
    return AuditService()


def credit(amount: str) -> AuditableEntry:
    return AuditableEntry(amount=Decimal(amount), is_credit=True)


def debit(amount: str) -> AuditableEntry:
    return AuditableEntry(amount=Decimal(amount), is_credit=False)


def unknown(amount: str) -> AuditableEntry:
    return AuditableEntry(amount=Decimal(amount), is_credit=None)


class TestBuildQuery:
    def test_defaults_the_page_size(self, service: AuditService) -> None:
        assert service.build_query().limit == DEFAULT_PAGE_SIZE

    def test_accepts_the_maximum_page_size(self, service: AuditService) -> None:
        assert service.build_query(limit=MAX_PAGE_SIZE).limit == MAX_PAGE_SIZE

    def test_rejects_a_page_size_above_the_ceiling(
        self, service: AuditService
    ) -> None:
        with pytest.raises(InvalidAuditQueryError):
            service.build_query(limit=MAX_PAGE_SIZE + 1)

    @pytest.mark.parametrize("limit", [0, -1])
    def test_rejects_a_non_positive_page_size(
        self, service: AuditService, limit: int
    ) -> None:
        with pytest.raises(InvalidAuditQueryError):
            service.build_query(limit=limit)

    def test_rejects_a_negative_offset(self, service: AuditService) -> None:
        with pytest.raises(InvalidAuditQueryError):
            service.build_query(offset=-1)

    def test_rejects_an_inverted_window(self, service: AuditService) -> None:
        now = datetime.now(timezone.utc)
        with pytest.raises(InvalidAuditQueryError) as exc_info:
            service.build_query(occurred_from=now, occurred_to=now - timedelta(days=1))

        assert "occurred_from" in str(exc_info.value)

    def test_accepts_a_window_that_starts_and_ends_at_the_same_instant(
        self, service: AuditService
    ) -> None:
        now = datetime.now(timezone.utc)
        query = service.build_query(occurred_from=now, occurred_to=now)
        assert query.occurred_from == query.occurred_to == now

    def test_accepts_an_open_ended_window(self, service: AuditService) -> None:
        now = datetime.now(timezone.utc)
        assert service.build_query(occurred_from=now).occurred_to is None
        assert service.build_query(occurred_to=now).occurred_from is None

    def test_carries_the_filters_through(self, service: AuditService) -> None:
        query = service.build_query(wallet_id="w1", limit=10, offset=20)
        assert query.wallet_id == "w1"
        assert query.limit == 10
        assert query.offset == 20

    def test_an_invalid_query_is_an_audit_error(self) -> None:
        assert issubclass(InvalidAuditQueryError, AuditError)


class TestComputeBalance:
    def test_an_empty_ledger_implies_a_zero_balance(
        self, service: AuditService
    ) -> None:
        assert service.compute_balance([]) == Decimal("0")

    def test_credits_add_and_debits_subtract(self, service: AuditService) -> None:
        entries = [credit("100"), debit("30"), credit("5")]
        assert service.compute_balance(entries) == Decimal("75")

    def test_entries_of_unknown_direction_are_skipped(
        self, service: AuditService
    ) -> None:
        assert service.compute_balance([credit("100"), unknown("50")]) == Decimal(
            "100"
        )

    def test_arithmetic_is_exact(self, service: AuditService) -> None:
        # The whole reason money is Decimal: 0.1 + 0.2 must be 0.3
        # exactly, or a reconciliation would report a phantom
        # discrepancy of 5.5e-17.
        entries = [credit("0.1"), credit("0.2")]
        assert service.compute_balance(entries) == Decimal("0.3")

    def test_a_ledger_can_imply_a_negative_balance(
        self, service: AuditService
    ) -> None:
        # Not something the wallet rules permit, which is exactly why
        # the audit must be able to report it rather than assume it away.
        assert service.compute_balance([debit("10")]) == Decimal("-10")


class TestVerifyLedgerIntegrity:
    def test_a_ledger_that_matches_is_balanced(self, service: AuditService) -> None:
        report = service.verify_ledger_integrity(
            wallet_id="w1",
            recorded_balance=Decimal("75"),
            entries=[credit("100"), debit("25")],
        )

        assert report.is_balanced
        assert report.discrepancy == Decimal("0")
        assert report.computed_balance == Decimal("75")
        assert report.entries_examined == 2
        assert report.unverifiable_entries == 0

    def test_reports_a_shortfall_when_the_balance_exceeds_the_ledger(
        self, service: AuditService
    ) -> None:
        # Money appeared without an entry to explain it.
        report = service.verify_ledger_integrity(
            wallet_id="w1",
            recorded_balance=Decimal("100"),
            entries=[credit("60")],
        )

        assert not report.is_balanced
        assert report.discrepancy == Decimal("40")

    def test_reports_a_negative_discrepancy_the_other_way_round(
        self, service: AuditService
    ) -> None:
        # An entry exists that no balance change matches.
        report = service.verify_ledger_integrity(
            wallet_id="w1",
            recorded_balance=Decimal("60"),
            entries=[credit("100")],
        )

        assert report.discrepancy == Decimal("-40")
        assert not report.is_balanced

    def test_both_legs_of_a_transfer_reconcile_from_the_ledger_alone(
        self, service: AuditService
    ) -> None:
        # The case that motivated recording a direction: both legs
        # share a type and a positive amount, so without direction the
        # sender's ledger would replay to +100 instead of -100.
        sender = service.verify_ledger_integrity(
            wallet_id="sender",
            recorded_balance=Decimal("900"),
            entries=[credit("1000"), debit("100")],
        )
        receiver = service.verify_ledger_integrity(
            wallet_id="receiver",
            recorded_balance=Decimal("100"),
            entries=[credit("100")],
        )

        assert sender.is_balanced
        assert receiver.is_balanced

    def test_an_unverifiable_entry_makes_the_result_inconclusive(
        self, service: AuditService
    ) -> None:
        # Even though the remaining entries happen to reconcile, the
        # skipped one means we cannot claim the ledger accounts for the
        # balance. Reporting "balanced" here would be the single most
        # misleading thing this API could do.
        report = service.verify_ledger_integrity(
            wallet_id="w1",
            recorded_balance=Decimal("100"),
            entries=[credit("100"), unknown("40")],
        )

        assert report.unverifiable_entries == 1
        assert report.discrepancy == Decimal("0")
        assert not report.is_balanced

    def test_counts_every_unverifiable_entry(self, service: AuditService) -> None:
        report = service.verify_ledger_integrity(
            wallet_id="w1",
            recorded_balance=Decimal("0"),
            entries=[unknown("1"), unknown("2"), credit("0")],
        )

        assert report.entries_examined == 3
        assert report.unverifiable_entries == 2

    def test_an_empty_ledger_reconciles_only_with_a_zero_balance(
        self, service: AuditService
    ) -> None:
        assert service.verify_ledger_integrity(
            wallet_id="w1", recorded_balance=Decimal("0"), entries=[]
        ).is_balanced

        assert not service.verify_ledger_integrity(
            wallet_id="w1", recorded_balance=Decimal("1"), entries=[]
        ).is_balanced

    def test_echoes_the_wallet_id_into_the_report(
        self, service: AuditService
    ) -> None:
        report = service.verify_ledger_integrity(
            wallet_id="wallet-42", recorded_balance=Decimal("0"), entries=[]
        )
        assert report.wallet_id == "wallet-42"

    def test_reports_rather_than_raises_on_a_mismatch(
        self, service: AuditService
    ) -> None:
        # A discrepancy is a finding to investigate, not an error that
        # should abort the request that discovered it.
        report = service.verify_ledger_integrity(
            wallet_id="w1",
            recorded_balance=Decimal("999"),
            entries=[credit("1")],
        )
        assert report.discrepancy == Decimal("998")
