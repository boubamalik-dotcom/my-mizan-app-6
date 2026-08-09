"""Layer 3 — pure business logic for inspecting the append-only
transaction ledger.

STRICT RULE: no FastAPI, no Pydantic, no SQLAlchemy, and no imports
from Layers 2, 4, or 5. This module never reads the ledger itself; it
is handed entries that have already been fetched and decides what they
mean. That is what lets the reconciliation rules below be tested
exhaustively in memory, which for a compliance feature matters more
than for most code: the check is only worth having if it is itself
beyond doubt.

Money is `decimal.Decimal` throughout, never `float`, for the same
reason as in `layer_3_business/wallet/wallet_service.py` — a
reconciliation that disagreed with the ledger by a floating-point
rounding error would be worse than no reconciliation at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from .audit_exceptions import InvalidAuditQueryError

#: Page size used when a caller does not ask for one.
DEFAULT_PAGE_SIZE = 50

#: Hard ceiling on a single page. A regulator pulling a year of history
#: should paginate rather than ask one request to materialise it all.
MAX_PAGE_SIZE = 500


@dataclass(frozen=True, slots=True)
class AuditableEntry:
    """The minimum a ledger entry must tell us to be reconciled: how
    much, and in which direction.

    Deliberately *not* Layer 4's `LedgerEntryRecord`: importing that
    would point Layer 3 at Layer 4 and invert the dependency. Layer 2
    maps records into these, so this module stays free of any notion
    of how the ledger is stored.
    """

    amount: Decimal

    #: True when the entry increased the wallet's balance (a deposit,
    #: or the receiving leg of a transfer), False when it decreased it.
    #: `None` for an entry whose direction cannot be determined — see
    #: [LedgerIntegrityReport.unverifiable_entries].
    is_credit: Optional[bool]


@dataclass(frozen=True, slots=True)
class AuditQuery:
    """A validated ledger query.

    Only ever produced by [AuditService.build_query], so holding one is
    proof the bounds below were checked.
    """

    wallet_id: Optional[str]
    occurred_from: Optional[datetime]
    occurred_to: Optional[datetime]
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class LedgerIntegrityReport:
    """The result of reconciling a wallet's recorded balance against
    its ledger."""

    wallet_id: str

    #: The balance the wallet row claims.
    recorded_balance: Decimal

    #: The balance implied by replaying every ledger entry.
    computed_balance: Decimal

    #: `recorded_balance - computed_balance`. Zero when they agree.
    discrepancy: Decimal

    entries_examined: int

    #: Entries whose direction could not be determined, and which were
    #: therefore excluded from [computed_balance]. Any value above zero
    #: makes the reconciliation inconclusive rather than merely
    #: imprecise, so [is_balanced] is False regardless of the
    #: discrepancy.
    unverifiable_entries: int

    @property
    def is_balanced(self) -> bool:
        """Whether the ledger fully accounts for the recorded balance.

        Requires both that nothing was skipped and that the remainder
        reconciles exactly. Reporting "balanced" while having silently
        ignored entries would be the single most misleading thing this
        API could do.
        """
        return self.unverifiable_entries == 0 and self.discrepancy == Decimal("0")


class AuditService:
    """Validates audit queries and reconciles ledgers.

    Every method is deterministic and side-effect free.
    """

    def build_query(
        self,
        *,
        wallet_id: Optional[str] = None,
        occurred_from: Optional[datetime] = None,
        occurred_to: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> AuditQuery:
        """Validates and normalises the parameters of a ledger query.

        Args:
            wallet_id: Restrict to one wallet, or `None` for all.
            occurred_from: Inclusive lower bound on entry time.
            occurred_to: Inclusive upper bound on entry time.
            limit: Page size; defaults to [DEFAULT_PAGE_SIZE].
            offset: How many entries to skip.

        Returns:
            The validated [AuditQuery].

        Raises:
            InvalidAuditQueryError: If the window is inverted, the page
                size is outside 1..[MAX_PAGE_SIZE], or the offset is
                negative.
        """
        resolved_limit = DEFAULT_PAGE_SIZE if limit is None else limit

        if resolved_limit < 1:
            raise InvalidAuditQueryError("The page size must be at least 1.")
        if resolved_limit > MAX_PAGE_SIZE:
            raise InvalidAuditQueryError(
                f"The page size may not exceed {MAX_PAGE_SIZE}; "
                "paginate with `offset` for larger exports."
            )
        if offset < 0:
            raise InvalidAuditQueryError("The offset may not be negative.")

        if (
            occurred_from is not None
            and occurred_to is not None
            and occurred_from > occurred_to
        ):
            raise InvalidAuditQueryError(
                "`occurred_from` must not be later than `occurred_to`."
            )

        return AuditQuery(
            wallet_id=wallet_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            limit=resolved_limit,
            offset=offset,
        )

    def compute_balance(self, entries: Iterable[AuditableEntry]) -> Decimal:
        """Replays `entries` into the balance they imply.

        Credits add, debits subtract, and entries of unknown direction
        are skipped — [verify_ledger_integrity] is what reports how
        many were skipped, so this method's result is never read
        without that count alongside it.
        """
        balance = Decimal("0")
        for entry in entries:
            if entry.is_credit is True:
                balance += entry.amount
            elif entry.is_credit is False:
                balance -= entry.amount
        return balance

    def verify_ledger_integrity(
        self,
        *,
        wallet_id: str,
        recorded_balance: Decimal,
        entries: Sequence[AuditableEntry],
    ) -> LedgerIntegrityReport:
        """Reconciles a wallet's recorded balance against its ledger.

        This is the substance of "immutable ledger inspection": the
        ledger is append-only, so replaying it must reproduce the
        balance the wallet row claims. A discrepancy means the two
        disagree — either the balance was changed without a
        corresponding entry, or an entry was written that no balance
        change matches — and either is a finding worth escalating.

        Args:
            wallet_id: The wallet being reconciled, echoed into the
                report.
            recorded_balance: The balance stored on the wallet row.
            entries: Every ledger entry for that wallet. Passing a
                partial page would produce a meaningless discrepancy,
                so callers must pass the full history.

        Returns:
            A [LedgerIntegrityReport]. Note this *reports* rather than
            raises: a mismatch is a finding to be recorded and
            investigated, not an error that should abort the request
            that discovered it.
        """
        computed = self.compute_balance(entries)
        unverifiable = sum(1 for entry in entries if entry.is_credit is None)

        return LedgerIntegrityReport(
            wallet_id=wallet_id,
            recorded_balance=recorded_balance,
            computed_balance=computed,
            discrepancy=recorded_balance - computed,
            entries_examined=len(entries),
            unverifiable_entries=unverifiable,
        )
