"""Layer 2 — Audit controller.

Orchestrates regulatory inspection of the append-only ledger:

1. Calls Layer 3 (`AuditService`) to validate a query's bounds and to
   reconcile a ledger against a recorded balance — pure logic, no I/O.
2. Uses Layer 4 (`UnitOfWork`, `AuditRepository`) to read the ledger,
   and `UserRepository` for role administration.
3. Translates every domain exception from Layers 3/4 into the matching
   `HTTPException`, so this is the only place an audit domain error
   becomes an HTTP status code.

`audit_routes.py` stays a thin adapter over this class.

Note the direction of the mapping in [_to_auditable]: Layer 4's
records are converted *here*, on the way into Layer 3, because Layer 3
must not know that a ledger row or an ORM exists. Layer 2 is the only
layer that legitimately sees both.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Callable, Iterator, List, Optional, Sequence

from fastapi import HTTPException, status

from ...layer_3_business.audit.audit_exceptions import InvalidAuditQueryError
from ...layer_3_business.audit.audit_service import (
    AuditableEntry,
    AuditQuery,
    AuditService,
    LedgerIntegrityReport,
)
from ...layer_3_business.authz.authz_exceptions import InvalidRoleError
from ...layer_3_business.authz.roles import Role
from ...layer_4_data_access.repositories.audit_repository import (
    AuditLedgerEntry,
    AuditLedgerPage,
)
from ...layer_4_data_access.repositories.user_repository import (
    UserNotFoundError,
    UserRecord,
)
from ...layer_4_data_access.uow.transaction_manager import UnitOfWork
from ...layer_5_storage.models.transaction_ledger_model import (
    EntryDirection,
    TransactionType,
)


class AuditController:
    """Coordinates Layer 3 audit logic and Layer 4 read access to serve
    the Audit API."""

    def __init__(
        self,
        *,
        audit_service: AuditService,
        unit_of_work_factory: Callable[[], UnitOfWork] = UnitOfWork,
    ) -> None:
        """
        Args:
            audit_service: The Layer 3 service validating queries and
                reconciling ledgers.
            unit_of_work_factory: A zero-argument callable returning a
                fresh, not-yet-entered `UnitOfWork`. Injected so tests
                can point it at an isolated database.
        """
        self._audit_service = audit_service
        self._unit_of_work_factory = unit_of_work_factory

    async def query_ledger(
        self,
        *,
        wallet_id: Optional[str] = None,
        user_id: Optional[str] = None,
        transaction_type: Optional[TransactionType] = None,
        occurred_from: Optional[object] = None,
        occurred_to: Optional[object] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> tuple[AuditLedgerPage, AuditQuery]:
        """Returns a page of ledger entries matching the filters.

        The query's bounds are validated by Layer 3 *before* any
        database work, so a malformed window costs a 422 rather than a
        scan.

        Returns:
            The page, plus the validated query it was built from (whose
            normalised `limit`/`offset` the response echoes back).

        Raises:
            HTTPException: 422 if the query is not answerable.
        """
        with self._translate_domain_errors():
            query = self._audit_service.build_query(
                wallet_id=wallet_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                limit=limit,
                offset=offset,
            )

        async with self._unit_of_work_factory() as uow:
            page = await uow.audit.query_ledger(
                wallet_id=query.wallet_id,
                user_id=user_id,
                transaction_type=transaction_type,
                occurred_from=query.occurred_from,
                occurred_to=query.occurred_to,
                limit=query.limit,
                offset=query.offset,
            )

        return page, query

    async def verify_wallet_integrity(
        self, wallet_id: str
    ) -> LedgerIntegrityReport:
        """Reconciles a wallet's recorded balance against its complete
        ledger.

        Reads the wallet and its entire history inside one unit of work
        so the two cannot be read either side of a concurrent
        transaction — a balance fetched before a deposit and a ledger
        fetched after it would report a phantom discrepancy and send an
        auditor chasing nothing.

        Raises:
            HTTPException: 404 if no such wallet exists.
        """
        async with self._unit_of_work_factory() as uow:
            wallet = await uow.wallets.get_wallet_by_id(wallet_id)
            if wallet is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f'Wallet "{wallet_id}" does not exist.',
                )
            entries = await uow.audit.list_all_entries_for_wallet(wallet_id)

        return self._audit_service.verify_ledger_integrity(
            wallet_id=wallet_id,
            recorded_balance=wallet.balance,
            entries=self._to_auditable(entries),
        )

    async def reconstruct_transfer(
        self, reference_id: str
    ) -> tuple[Sequence[AuditLedgerEntry], bool]:
        """Returns every entry sharing `reference_id`, with whether
        they form a well-shaped transfer.

        Returns:
            The entries, and a flag that is true only for exactly one
            debit and one credit of equal amount.

        Raises:
            HTTPException: 404 if the reference matches no entries.
        """
        async with self._unit_of_work_factory() as uow:
            entries = await uow.audit.list_entries_by_reference(reference_id)

        if not entries:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'No ledger entries reference "{reference_id}".',
            )

        return entries, self._is_well_formed_transfer(entries)

    async def set_user_role(self, *, user_id: str, role: Role) -> UserRecord:
        """Assigns `role` to a user account.

        Raises:
            HTTPException: 404 if no such user exists.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                user = await uow.users.set_user_role(user_id, role=role.value)
                await uow.commit()
        return user

    async def get_user(self, user_id: str) -> UserRecord:
        """Fetches one user account.

        Raises:
            HTTPException: 404 if no such user exists.
        """
        async with self._unit_of_work_factory() as uow:
            user = await uow.users.get_user_by_id(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'No user exists with id "{user_id}".',
            )
        return user

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _to_auditable(
        entries: Sequence[AuditLedgerEntry],
    ) -> List[AuditableEntry]:
        """Maps Layer 4 ledger records into the minimal shape Layer 3
        reconciles.

        This mapping is why `AuditService` needs no knowledge of the
        ledger's storage: it receives amounts and directions, nothing
        more. An entry whose direction is unknown carries `None`, which
        the service counts as unverifiable rather than assuming.
        """
        return [
            AuditableEntry(
                amount=entry.amount,
                is_credit=(
                    None
                    if entry.direction is None
                    else entry.direction is EntryDirection.CREDIT
                ),
            )
            for entry in entries
        ]

    @staticmethod
    def _is_well_formed_transfer(entries: Sequence[AuditLedgerEntry]) -> bool:
        """Whether `entries` form exactly one debit and one credit of
        equal amount — the shape a transfer must have if both legs were
        written.

        A reference resolving to anything else (one leg only, three
        entries, mismatched amounts) means money moved without a
        balanced counterpart, which is exactly the sort of finding an
        audit exists to surface.
        """
        if len(entries) != 2:
            return False

        debits = [e for e in entries if e.direction is EntryDirection.DEBIT]
        credits = [e for e in entries if e.direction is EntryDirection.CREDIT]
        if len(debits) != 1 or len(credits) != 1:
            return False

        return Decimal(debits[0].amount) == Decimal(credits[0].amount)

    @staticmethod
    @contextmanager
    def _translate_domain_errors() -> Iterator[None]:
        """Translates the domain exceptions Layers 3/4 raise here into
        the matching `HTTPException`.

        Mapping:

        * `InvalidAuditQueryError` -> 422 Unprocessable Entity
        * `InvalidRoleError` -> 422 Unprocessable Entity
        * `UserNotFoundError` -> 404 Not Found
        """
        try:
            yield
        except InvalidAuditQueryError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except InvalidRoleError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except UserNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
