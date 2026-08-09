"""Layer 3 — pure domain exceptions for Mizan Door's clinic queues.

Plain Python exceptions with no framework imports: Layer 2's
`QueueController` is the only place that turns these into HTTP status
codes, so the same rules could be driven from a CLI or a background
job without dragging FastAPI along.
"""
from __future__ import annotations


class QueueDomainError(Exception):
    """Base class for every clinic-queue business-rule violation."""


class ClinicNotAcceptingPatientsError(QueueDomainError):
    """Raised when someone tries to join a clinic that has stopped
    admitting patients — full for the day, closed, or on a break.

    Distinct from "no such clinic": the clinic exists and is listed,
    it is simply not taking anyone right now, and the patient should
    be told that rather than shown a generic failure.
    """

    def __init__(self, clinic_id: str) -> None:
        """
        Args:
            clinic_id: The clinic that refused the reservation.
        """
        self.clinic_id = clinic_id
        super().__init__(
            f'Clinic "{clinic_id}" is not accepting patients right now.'
        )


class AlreadyInQueueError(QueueDomainError):
    """Raised when a patient who already holds an active place in a
    clinic's queue tries to take a second one.

    One patient occupying two tickets would make the queue lie about
    how many people are really waiting, and would let one person hold
    two slots while others wait for one.
    """

    def __init__(self, clinic_id: str, user_id: str) -> None:
        """
        Args:
            clinic_id: The clinic in whose queue the patient already
                holds a place.
            user_id: The patient.
        """
        self.clinic_id = clinic_id
        self.user_id = user_id
        super().__init__(
            f'User "{user_id}" already holds an active place in clinic '
            f'"{clinic_id}"\'s queue.'
        )


class ReservationNotActiveError(QueueDomainError):
    """Raised when an operation that only makes sense for a place still
    in the queue is attempted on one that has already been served or
    cancelled.

    Cancelling an already-served reservation is not a no-op worth
    hiding: it means the caller is acting on a stale view of the queue,
    and silently succeeding would confirm a belief that is wrong.
    """

    def __init__(self, reservation_id: str, status: str) -> None:
        """
        Args:
            reservation_id: The reservation that is no longer active.
            status: Its current terminal status.
        """
        self.reservation_id = reservation_id
        self.status = status
        super().__init__(
            f'Reservation "{reservation_id}" is no longer active '
            f'(status: "{status}").'
        )
