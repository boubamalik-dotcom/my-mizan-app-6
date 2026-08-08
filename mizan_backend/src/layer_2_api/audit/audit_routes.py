"""Layer 2 — Audit API routes: role-gated, read-only inspection of the
append-only transaction ledger.

Routes here are intentionally thin: they parse transport-level input,
delegate to `AuditController`, and shape the result into a response
model. Every rule they enforce lives in Layer 3.

Two properties hold across this whole router by construction:

* **Nothing here writes to the ledger.** The only dependency available
  is `AuditRepository`, which exposes no append, update, or delete —
  so an audit request cannot alter the evidence it inspects.
* **Every route is permission-gated**, not merely authenticated. The
  ledger contains every user's financial history, so ordinary
  authentication is nowhere near sufficient.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, Request, status

from ...layer_3_business.authz.roles import Permission, Role
from ...layer_4_data_access.repositories.audit_repository import AuditLedgerEntry
from ...layer_4_data_access.repositories.user_repository import UserRecord
from ...layer_5_storage.models.transaction_ledger_model import TransactionType
from ..auth.deps import require_permission
from ..schemas.chat_schemas import ErrorResponse
from .audit_controller import AuditController
from .audit_schemas import (
    LedgerEntryResponse,
    LedgerIntegrityResponse,
    LedgerPageResponse,
    TransferReconstructionResponse,
    UpdateUserRoleRequest,
    UserRoleResponse,
)

router = APIRouter(prefix="/audit", tags=["audit"])

#: Shared by every route below: 401 when unauthenticated, 403 when the
#: caller's role lacks the required permission.
_AUTHZ_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing or invalid token."},
    403: {
        "model": ErrorResponse,
        "description": "The caller's role lacks the required permission.",
    },
}


def get_audit_controller(request: Request) -> AuditController:
    """Resolves the app-wide `AuditController` singleton, constructed
    once at startup in `main.py` (the composition root)."""
    return request.app.state.audit_controller


def _to_entry_response(entry: AuditLedgerEntry) -> LedgerEntryResponse:
    """Maps a Layer 4 ledger record to its API representation."""
    return LedgerEntryResponse(
        id=entry.id,
        wallet_id=entry.wallet_id,
        user_id=entry.user_id,
        amount=entry.amount,
        transaction_type=entry.transaction_type,
        direction=entry.direction,
        reference_id=entry.reference_id,
        counterparty_wallet_id=entry.counterparty_wallet_id,
        created_at=entry.created_at,
    )


@router.get(
    "/ledger",
    response_model=LedgerPageResponse,
    responses={
        **_AUTHZ_RESPONSES,
        422: {"model": ErrorResponse, "description": "The query is not answerable."},
    },
    summary="Inspect the append-only transaction ledger",
)
async def query_ledger(
    wallet_id: Optional[str] = Query(
        default=None, description="Restrict to a single wallet."
    ),
    user_id: Optional[str] = Query(
        default=None, description="Restrict to every wallet owned by one user."
    ),
    transaction_type: Optional[TransactionType] = Query(
        default=None, description="Restrict to one kind of movement."
    ),
    occurred_from: Optional[datetime] = Query(
        default=None, description="Inclusive lower bound on entry time."
    ),
    occurred_to: Optional[datetime] = Query(
        default=None, description="Inclusive upper bound on entry time."
    ),
    limit: Optional[int] = Query(
        default=None, description="Page size (1-500; defaults to 50)."
    ),
    offset: int = Query(default=0, description="Entries to skip."),
    controller: AuditController = Depends(get_audit_controller),
    _: UserRecord = Depends(require_permission(Permission.AUDIT_READ_LEDGER)),
) -> LedgerPageResponse:
    """Returns ledger entries matching every supplied filter, oldest
    first.

    Ordering is stable (`created_at`, then `id`), so paging through a
    long export cannot skip or repeat an entry — entries written inside
    one transaction can share a timestamp.

    Requires `audit:read_ledger`, held by auditors and admins. An
    ordinary user cannot reach this endpoint even for their own wallet;
    their own history is available through the Wallet API instead.
    """
    page, query = await controller.query_ledger(
        wallet_id=wallet_id,
        user_id=user_id,
        transaction_type=transaction_type,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )

    return LedgerPageResponse(
        entries=[_to_entry_response(entry) for entry in page.entries],
        total=page.total,
        limit=query.limit,
        offset=query.offset,
    )


@router.get(
    "/wallets/{wallet_id}/integrity",
    response_model=LedgerIntegrityResponse,
    responses={
        **_AUTHZ_RESPONSES,
        404: {"model": ErrorResponse, "description": "No such wallet."},
    },
    summary="Reconcile a wallet's balance against its ledger",
)
async def verify_wallet_integrity(
    wallet_id: str = Path(..., description="The wallet to reconcile."),
    controller: AuditController = Depends(get_audit_controller),
    _: UserRecord = Depends(require_permission(Permission.AUDIT_READ_LEDGER)),
) -> LedgerIntegrityResponse:
    """Replays a wallet's entire ledger and compares the result with
    the balance the wallet row claims.

    This is the substance of ledger inspection: because the ledger is
    append-only, replaying it *must* reproduce the recorded balance. A
    non-zero `discrepancy` means the two disagree — a balance changed
    without a matching entry, or an entry written with no matching
    balance change — and either is a finding worth escalating.

    Answers 200 with `is_balanced: false` rather than an error status
    when a wallet fails to reconcile: a discrepancy is a *result* of
    the inspection, not a failure to perform it.
    """
    report = await controller.verify_wallet_integrity(wallet_id)

    return LedgerIntegrityResponse(
        wallet_id=report.wallet_id,
        recorded_balance=report.recorded_balance,
        computed_balance=report.computed_balance,
        discrepancy=report.discrepancy,
        entries_examined=report.entries_examined,
        unverifiable_entries=report.unverifiable_entries,
        is_balanced=report.is_balanced,
    )


@router.get(
    "/transfers/{reference_id}",
    response_model=TransferReconstructionResponse,
    responses={
        **_AUTHZ_RESPONSES,
        404: {"model": ErrorResponse, "description": "No entries for that reference."},
    },
    summary="Reconstruct both legs of a transfer",
)
async def reconstruct_transfer(
    reference_id: str = Path(..., description="The transfer's correlation id."),
    controller: AuditController = Depends(get_audit_controller),
    _: UserRecord = Depends(require_permission(Permission.AUDIT_READ_LEDGER)),
) -> TransferReconstructionResponse:
    """Returns every entry sharing a reference id — for a transfer,
    both sides of the movement.

    `is_well_formed` is true only for exactly one debit and one credit
    of equal amount. Anything else means money moved without a balanced
    counterpart, which is precisely what an investigator is looking
    for.
    """
    entries, is_well_formed = await controller.reconstruct_transfer(reference_id)

    return TransferReconstructionResponse(
        reference_id=reference_id,
        entries=[_to_entry_response(entry) for entry in entries],
        is_well_formed=is_well_formed,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserRoleResponse,
    responses={
        **_AUTHZ_RESPONSES,
        404: {"model": ErrorResponse, "description": "No such user."},
    },
    summary="Read a user's assigned role",
)
async def get_user_role(
    user_id: str = Path(..., description="The account to inspect."),
    controller: AuditController = Depends(get_audit_controller),
    _: UserRecord = Depends(require_permission(Permission.MANAGE_USER_ROLES)),
) -> UserRoleResponse:
    """Returns one account's identity and current role. Requires
    `users:manage_roles`, so an auditor cannot enumerate who holds
    which role."""
    user = await controller.get_user(user_id)
    return UserRoleResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=Role.parse(user.role),
        is_active=user.is_active,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=UserRoleResponse,
    responses={
        **_AUTHZ_RESPONSES,
        404: {"model": ErrorResponse, "description": "No such user."},
        422: {"model": ErrorResponse, "description": "Unrecognised role."},
    },
    summary="Assign a role to a user",
)
async def update_user_role(
    payload: UpdateUserRoleRequest,
    user_id: str = Path(..., description="The account whose role is changing."),
    controller: AuditController = Depends(get_audit_controller),
    _: UserRecord = Depends(require_permission(Permission.MANAGE_USER_ROLES)),
) -> UserRoleResponse:
    """Grants `role` to a user.

    Requires `users:manage_roles`, which only an admin holds — an
    auditor deliberately cannot reach this, so read-only oversight
    cannot quietly escalate itself into write access.

    The first admin cannot be created this way, by construction. It is
    bootstrapped from the `BOOTSTRAP_ADMIN_EMAILS` setting at
    registration time; see `config.Settings.bootstrap_admin_emails`.
    """
    user = await controller.set_user_role(user_id=user_id, role=payload.role)
    return UserRoleResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=Role.parse(user.role),
        is_active=user.is_active,
    )


@router.get(
    "/roles",
    response_model=List[dict],
    responses=_AUTHZ_RESPONSES,
    status_code=status.HTTP_200_OK,
    summary="List the access-control policy",
)
async def list_roles(
    _: UserRecord = Depends(require_permission(Permission.AUDIT_READ_LEDGER)),
) -> List[dict]:
    """Returns every role and the permissions it holds.

    The policy itself is the compliance artifact a reviewer asks for
    first, so it is served from the same table the guards enforce
    (`ROLE_PERMISSIONS`) rather than from documentation that could
    drift away from the code.
    """
    from ...layer_3_business.authz.roles import ROLE_PERMISSIONS

    return [
        {
            "role": role.value,
            "permissions": sorted(
                permission.value for permission in ROLE_PERMISSIONS[role]
            ),
        }
        for role in Role
    ]
