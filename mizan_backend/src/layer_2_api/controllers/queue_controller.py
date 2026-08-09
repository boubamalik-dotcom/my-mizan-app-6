"""Layer 2 — Mizan Door clinic-queue controller.

`QueueController` orchestrates the queue use cases, mirroring
`WalletController`:

1. Uses Layer 4 (`UnitOfWork`, `QueueRepository`) to read queues and to
   take or give up a place, each inside a single transaction. Joining
   is one atomic call precisely because the row lock that makes ticket
   numbering safe must be held across the read and the insert (see
   `QueueRepository.join_queue`) — splitting it across two calls here
   would hold the lock correctly only by accident.
2. Enforces ownership: a reservation may only be cancelled by the
   patient who holds it, checked here before any write, exactly as
   `WalletController._require_ownership` does for wallets.
3. Catches every domain exception raised by Layers 3/4 and translates
   it into the matching `HTTPException`, so this is the only place a
   queue domain error becomes an HTTP status code.

`queue_routes.py` stays a thin adapter over this class.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from fastapi import HTTPException, status

from ...layer_3_business.queue.exceptions import (
    AlreadyInQueueError,
    ClinicNotAcceptingPatientsError,
    ReservationNotActiveError,
)
from ...layer_4_data_access.repositories.queue_repository import (
    ClinicNotFoundError,
    ClinicQueueRecord,
    ReservationNotFoundError,
    ReservationRecord,
    TicketNumberCollisionError,
)
from ...layer_4_data_access.uow.transaction_manager import UnitOfWork


class QueueController:
    """Coordinates Layer 3 queue rules and Layer 4 transactional
    persistence to serve Mizan Door's REST endpoints."""

    def __init__(
        self,
        *,
        unit_of_work_factory: Callable[[], UnitOfWork] = UnitOfWork,
    ) -> None:
        """
        Args:
            unit_of_work_factory: A zero-argument callable returning a
                fresh, not-yet-entered `UnitOfWork` each time it is
                invoked. Defaults to the `UnitOfWork` class itself.
                Injected so tests can point every unit of work this
                controller opens at an isolated test database.

        Note there is no `queue_service` parameter, unlike
        `WalletController`. The Layer 3 rules are consulted from inside
        `QueueRepository.join_queue`, because every one of them has to
        be evaluated while the clinic row lock is held; a copy injected
        here would have nothing left to decide.
        """
        self._unit_of_work_factory = unit_of_work_factory

    # -- Reads ------------------------------------------------------------

    async def list_queues(
        self, *, current_user_id: Optional[str] = None
    ) -> tuple[list[ClinicQueueRecord], Optional[ReservationRecord]]:
        """Lists every clinic's queue, plus the caller's own place if
        they have one.

        Args:
            current_user_id: The authenticated caller, or `None` for an
                anonymous request. Anonymous callers still get the
                queues — a patient deciding whether it is worth leaving
                the house should not have to sign in first — but no
                reservation, since there is nobody to attribute one to.

        Returns:
            A `(queues, reservation)` pair; `reservation` is `None`
            when the caller is anonymous or holds no active place.
        """
        async with self._unit_of_work_factory() as uow:
            queues = await uow.queues.get_clinics_with_queue_status()
            reservation = (
                await uow.queues.get_active_reservation_for_user(current_user_id)
                if current_user_id is not None
                else None
            )

        return queues, reservation

    # -- Writes -----------------------------------------------------------

    async def join_queue(
        self, *, clinic_id: str, current_user_id: str
    ) -> ReservationRecord:
        """Takes the next place in `clinic_id`'s queue for the
        authenticated caller.

        No ownership check applies: the reservation is created *for*
        `current_user_id`, so it belongs to them by construction.

        Args:
            clinic_id: The clinic to queue at.
            current_user_id: The authenticated caller.

        Returns:
            The newly held place.

        Raises:
            HTTPException: 404 if the clinic does not exist; 409 if the
                caller already holds a place there; 422 if the clinic
                has stopped admitting patients; 503 if a ticket
                collision means the request should be retried.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                reservation = await uow.queues.join_queue(
                    clinic_id=clinic_id, user_id=current_user_id
                )
                await uow.commit()

        return reservation

    async def cancel_reservation(
        self, *, reservation_id: str, current_user_id: str
    ) -> ReservationRecord:
        """Gives up the caller's place in a queue.

        Ownership is enforced before anything is written: a
        reservation belonging to someone else is refused with **403**,
        not silently cancelled. Both the lookup and the cancellation
        happen inside one transaction, so the reservation cannot be
        cancelled by another request in the window between them.

        Args:
            reservation_id: The place to give up.
            current_user_id: The authenticated caller.

        Returns:
            The cancelled reservation.

        Raises:
            HTTPException: 404 if no such reservation exists; 403 if it
                belongs to someone else; 410 if it was already served
                or cancelled.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                existing = await uow.queues.get_reservation_by_id(reservation_id)
                if existing is None:
                    raise ReservationNotFoundError(reservation_id)
                self._require_ownership(existing, current_user_id)

                reservation = await uow.queues.cancel_reservation(reservation_id)
                await uow.commit()

        return reservation

    # -- Internal helpers -------------------------------------------------

    @staticmethod
    def _require_ownership(
        reservation: ReservationRecord, current_user_id: str
    ) -> None:
        """Refuses any attempt to act on someone else's place in a
        queue.

        A deliberate **403** rather than a 404: within Mizan Door a
        reservation id is not a secret worth hiding behind a "does not
        exist" fiction, and telling a caller plainly that a place is
        not theirs is more useful than pretending the queue is empty.
        """
        if reservation.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

    @staticmethod
    @contextmanager
    def _translate_domain_errors() -> Iterator[None]:
        """Context manager translating every domain exception Layers
        3/4 can raise into the matching `HTTPException`.

        Mapping, chosen to line up with the Arabic messages
        `mizan_frontend`'s `QueueRepositoryImpl._mapReservationError`
        already shows for each code:

        * `ClinicNotFoundError` -> 404 Not Found
        * `ReservationNotFoundError` -> 404 Not Found
        * `AlreadyInQueueError` -> 409 Conflict
        * `ReservationNotActiveError` -> 410 Gone
        * `ClinicNotAcceptingPatientsError` -> 422 Unprocessable Entity
        * `TicketNumberCollisionError` -> 503 Service Unavailable
        """
        try:
            yield
        except ClinicNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except ReservationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except AlreadyInQueueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
        except ReservationNotActiveError as exc:
            # Gone rather than Conflict: the place did exist and no
            # longer does, which is precisely what 410 means, and it
            # lets the client tell "your booking expired" apart from
            # "you already have one".
            raise HTTPException(
                status_code=status.HTTP_410_GONE, detail=str(exc)
            ) from exc
        except ClinicNotAcceptingPatientsError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except TicketNumberCollisionError as exc:
            # Retryable and not the caller's fault, so 503 with a
            # Retry-After rather than a 409 that invites the client to
            # treat it as a permanent refusal.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
                headers={"Retry-After": "1"},
            ) from exc
