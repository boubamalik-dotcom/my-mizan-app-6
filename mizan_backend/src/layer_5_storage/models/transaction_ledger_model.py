"""Layer 5 — SQLAlchemy ORM model for the Digital Wallet's append-only
transaction ledger.

STRICT RULE: this module contains an ORM model only. It has zero
imports from Layers 2, 3, or 4.

Immutability is enforced, not just documented: an ORM-level
``before_update``/``before_delete`` event listener raises
`LedgerEntryImmutableError` if any code path ever attempts to mutate
or delete a persisted ledger row, so "append-only" is a property the
database session actively defends rather than a convention that can
be silently violated by a future bug. A financial audit trail is only
as trustworthy as its tamper-resistance — correcting a mistake means
appending an offsetting entry, never rewriting history.
"""
from __future__ import annotations

import enum
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, event
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..base_model import Base, TimestampMixin, generate_uuid
from .wallet_model import MONEY_PRECISION, MONEY_SCALE


class LedgerEntryImmutableError(Exception):
    """Raised when application code attempts to ``UPDATE`` or
    ``DELETE`` a persisted `TransactionLedgerModel` row."""

    def __init__(self, entry_id: object, operation: str) -> None:
        """
        Args:
            entry_id: The primary key of the ledger row that code
                tried to mutate/delete.
            operation: The rejected operation, either `"UPDATE"` or
                `"DELETE"`.
        """
        self.entry_id = entry_id
        self.operation = operation
        super().__init__(
            f"Ledger entry {entry_id!r} is immutable and append-only; "
            f"{operation} is not permitted. Correct history by "
            "appending an offsetting entry, never by mutating one."
        )


class TransactionType(str, enum.Enum):
    """Every kind of balance-affecting event this ledger records."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"


class TransactionLedgerModel(Base, TimestampMixin):
    """A single, immutable record of one balance-affecting event.

    `amount` is always a positive magnitude — direction/kind is
    conveyed by `transaction_type`, matching
    `WalletService`'s convention that every validated amount is
    strictly positive (see `layer_3_business/wallet/wallet_service.py`).

    For a `TRANSFER`, two rows are written — one for the sending
    wallet, one for the receiving wallet — correlated by sharing the
    same `reference_id` and each naming the other via
    `counterparty_wallet_id`, so the full transfer can always be
    reconstructed from the ledger alone.
    """

    __tablename__ = "transaction_ledger"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        Index("ix_ledger_wallet_id_created_at", "wallet_id", "created_at"),
        Index("ix_ledger_reference_id", "reference_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    wallet_id: Mapped[str] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SqlEnum(TransactionType, name="transaction_type", native_enum=False),
        nullable=False,
    )
    #: Correlates the two legs of a transfer (or, more generally, any
    #: group of related entries); a plain marker, not a foreign key,
    #: since a transfer's two rows reference each other symmetrically
    #: rather than one owning the other. `created_at` (from
    #: `TimestampMixin`) is always present regardless, so an entry can
    #: be placed in time even without a `reference_id`.
    reference_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: For a `TRANSFER` entry, the wallet on the other side of the
    #: transfer. `None` for deposits and withdrawals.
    counterparty_wallet_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        """Compact representation for logs/debuggers, not part of any
        public API contract."""
        return (
            f"TransactionLedgerModel(id={self.id!r}, wallet_id={self.wallet_id!r}, "
            f"transaction_type={self.transaction_type!r}, amount={self.amount!r})"
        )


@event.listens_for(TransactionLedgerModel, "before_update")
def _reject_ledger_update(mapper, connection, target: TransactionLedgerModel) -> None:
    """Enforces append-only semantics at the ORM level: no code path,
    however deeply nested, may modify a persisted ledger row."""
    raise LedgerEntryImmutableError(target.id, "UPDATE")


@event.listens_for(TransactionLedgerModel, "before_delete")
def _reject_ledger_delete(mapper, connection, target: TransactionLedgerModel) -> None:
    """Enforces append-only semantics at the ORM level: no code path,
    however deeply nested, may delete a persisted ledger row."""
    raise LedgerEntryImmutableError(target.id, "DELETE")
