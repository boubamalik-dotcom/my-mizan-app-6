"""Layer 5 — SQLAlchemy ORM model for the Digital Wallet's core
account record.

STRICT RULE: this module contains an ORM model only. It has zero
imports from Layers 2, 3, or 4 — it knows nothing about business
rules, HTTP, or how it is accessed; `layer_4_data_access/repositories/
wallet_repository.py` is the only code elsewhere in the backend that
imports this model, and it alone is responsible for translating rows
here into plain data that Layers 2/3 can consume.

Optimistic concurrency control: `version` is registered as this
model's ``version_id_col``. SQLAlchemy appends ``AND version =
:version`` to every ``UPDATE`` statement it issues for this model and
atomically increments the column, raising
`sqlalchemy.orm.exc.StaleDataError` if zero rows matched — i.e.
another transaction already changed this exact row since it was read.
This is what prevents a *lost update*: two concurrent transactions
that both read balance ``100``, one computing ``100 - 30`` and the
other ``100 - 50``, can no longer both blindly write their result and
have the second write silently clobber the first — whichever commits
second finds its expected version gone and fails loudly instead.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base_model import Base, TimestampMixin, generate_uuid

#: Fixed-point precision for every monetary column: 18 total digits,
#: 4 after the decimal point — deliberately more precise than any
#: currency this system currently supports, so adding a
#: higher-precision currency later never requires a schema migration
#: to widen the column.
MONEY_PRECISION = 18
MONEY_SCALE = 4


class WalletModel(Base, TimestampMixin):
    """A single user's balance in a single currency.

    ``user_id`` is a real foreign key into ``users.id`` — every wallet
    is owned by exactly one registered account, which is what lets
    `WalletController` enforce "you may only act on your own wallet"
    (see `layer_2_api/controllers/wallet_controller.py`). This module
    deliberately does not import `UserModel` (only its table/column
    name as a string), so `wallet_model.py` and `user_model.py` never
    need to know about each other directly, avoiding a circular
    import between two sibling Layer 5 modules.

    ``is_locked`` mirrors the boolean flag
    `layer_3_business.wallet.wallet_service.WalletService
    .ensure_wallet_is_unlocked` expects Layer 2 to supply — this layer
    deliberately does not invent a richer status enum, so Layer 4/2
    can pass this column's value straight through to Layer 3 without
    any translation step.
    """

    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_wallet_user_currency"),
        CheckConstraint("balance >= 0", name="ck_wallet_balance_non_negative"),
        CheckConstraint("version >= 0", name="ck_wallet_version_non_negative"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False, default=Decimal("0")
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Optimistic-locking version counter, managed entirely by
    #: SQLAlchemy via `__mapper_args__["version_id_col"]` below.
    #: Application code should treat this column as read-only.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __mapper_args__ = {"version_id_col": version}

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        """Compact representation for logs/debuggers, not part of any
        public API contract."""
        return (
            f"WalletModel(id={self.id!r}, user_id={self.user_id!r}, "
            f"currency={self.currency!r}, balance={self.balance!r}, "
            f"version={self.version!r})"
        )
