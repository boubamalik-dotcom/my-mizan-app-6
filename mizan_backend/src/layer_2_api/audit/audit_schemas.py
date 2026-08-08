"""Layer 2 — Pydantic request/response contracts for the Audit API.

These schemas are the API's public contract, versioned independently of
Layer 4's `AuditLedgerEntry` and Layer 3's `LedgerIntegrityReport` so
either can change without breaking a regulator's tooling.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from ...layer_3_business.authz.roles import Role
from ...layer_5_storage.models.transaction_ledger_model import (
    EntryDirection,
    TransactionType,
)


class LedgerEntryResponse(BaseModel):
    """One immutable ledger entry, as returned to an auditor."""

    id: str
    wallet_id: str
    #: The wallet owner, resolved server-side so an auditor can
    #: attribute an entry without a second lookup.
    user_id: str
    amount: Decimal
    transaction_type: TransactionType
    #: `null` only for entries written before the direction column
    #: existed; such entries cannot be reconciled and are counted as
    #: unverifiable by the integrity check.
    direction: Optional[EntryDirection]
    #: Shared by both legs of a transfer, so the pair can be
    #: reconstructed via `GET /audit/transfers/{reference_id}`.
    reference_id: Optional[str]
    counterparty_wallet_id: Optional[str]
    created_at: datetime


class LedgerPageResponse(BaseModel):
    """A page of ledger entries plus the total matching the query."""

    entries: List[LedgerEntryResponse]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        """Whether entries remain beyond this page."""
        return self.offset + len(self.entries) < self.total


class LedgerIntegrityResponse(BaseModel):
    """The result of reconciling a wallet's balance against its
    ledger."""

    wallet_id: str
    recorded_balance: Decimal
    computed_balance: Decimal
    #: `recorded_balance - computed_balance`; zero when they agree.
    discrepancy: Decimal
    entries_examined: int
    #: Entries excluded from the computation because their direction is
    #: unknown. Any value above zero makes the result inconclusive.
    unverifiable_entries: int
    #: True only when nothing was skipped *and* the remainder
    #: reconciles exactly.
    is_balanced: bool


class TransferReconstructionResponse(BaseModel):
    """Both legs of a transfer, correlated by reference id."""

    reference_id: str
    entries: List[LedgerEntryResponse]
    #: True when the reference resolves to exactly one debit and one
    #: credit of equal amount — the shape a well-formed transfer must
    #: have. False flags a movement worth investigating.
    is_well_formed: bool


class UpdateUserRoleRequest(BaseModel):
    """Body for `PATCH /audit/users/{user_id}/role`."""

    role: Role = Field(
        ...,
        description="The role to assign. Validated against the closed "
        "set of known roles, so a typo is rejected rather than "
        "silently granting or denying access.",
    )

    model_config = {"json_schema_extra": {"examples": [{"role": "auditor"}]}}


class UserRoleResponse(BaseModel):
    """A user's identity and current role."""

    id: str
    email: str
    full_name: str
    role: Role
    is_active: bool
