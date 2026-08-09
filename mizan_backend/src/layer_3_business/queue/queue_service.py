"""Layer 3 — pure business rules for Mizan Door's clinic queues.

STRICT RULE: pure Python only. No FastAPI, no SQLAlchemy, no Redis,
and nothing from Layers 2, 4, or 5 — every method here takes plain
values and returns plain values, so all of it is testable without a
database, an event loop, or an HTTP client.

The arithmetic is deliberately small. That is the point: keeping "what
ticket comes next" and "how long is that likely to take" out of the
SQL means the rules can be read, tested, and changed in one place,
while Layer 4 is left with nothing but the mechanics of doing it
atomically.
"""
from __future__ import annotations

import enum

from .exceptions import (
    AlreadyInQueueError,
    ClinicNotAcceptingPatientsError,
    ReservationNotActiveError,
)


class AdvanceOutcome(str, enum.Enum):
    """What happened when a clinic asked for the next patient.

    Three distinct results, because "nothing was called" is ambiguous
    on its own and the clinician needs to know which of the two it was:
    the last patient just finished and the room is now free, or there
    was never anybody there.
    """

    #: A patient was called in. Any previous consultation was completed.
    CALLED_NEXT = "called_next"
    #: The patient in the room was completed, and nobody was waiting to
    #: replace them. The queue is now empty.
    COMPLETED_LAST = "completed_last"
    #: Nobody was in the room and nobody was waiting; nothing changed.
    QUEUE_EMPTY = "queue_empty"


class QueueService:
    """Stateless collection of clinic-queue rules.

    Stateless and free of I/O, so a single shared instance is the whole
    object — the same pattern `AuthorizationService` uses in
    `layer_2_api/auth/deps.py`.
    """

    #: The ticket number handed to the very first patient of a clinic.
    #: One rather than zero because it is read aloud in a waiting room.
    FIRST_TICKET_NUMBER = 1

    # -- Ticket arithmetic ----------------------------------------------

    def next_ticket_number(self, highest_issued: int | None) -> int:
        """Returns the ticket number to hand to the next patient.

        Args:
            highest_issued: The highest ticket already issued by this
                clinic, or `None` if it has never issued one. Includes
                served and cancelled tickets deliberately — reusing the
                number of someone who cancelled would hand two patients
                the same ticket over the course of a day, and the
                clinic's own records would no longer be able to tell
                them apart.

        Returns:
            The next ticket number, always greater than every ticket
            this clinic has issued before.
        """
        if highest_issued is None:
            return self.FIRST_TICKET_NUMBER
        return highest_issued + 1

    # -- Wait-time estimation -------------------------------------------

    def estimate_wait_minutes(
        self, *, people_ahead: int, service_rate_minutes: int
    ) -> int:
        """Estimates how long a patient with `people_ahead` in front of
        them will wait.

        A deliberately simple model — queue length times the clinic's
        own measured pace. It is honest about being an estimate, and it
        has the property that patients can verify it themselves, which
        a cleverer model would lose.

        Args:
            people_ahead: How many active tickets are ahead. Zero means
                next to be seen.
            service_rate_minutes: How long this clinic currently takes
                per patient.

        Returns:
            The estimate in whole minutes. Never negative: a nonsensical
            input yields `0` rather than a negative wait, since the
            latter would render as a time in the past.
        """
        if people_ahead <= 0 or service_rate_minutes <= 0:
            return 0
        return people_ahead * service_rate_minutes

    # -- Advancing the queue ---------------------------------------------

    def classify_advance(
        self, *, had_patient_in_consultation: bool, has_next_waiting: bool
    ) -> AdvanceOutcome:
        """Decides what "call the next patient" amounts to, given what
        the queue currently holds.

        Both inputs are facts only Layer 4 can establish; deciding what
        they *mean* stays here, which is what makes the three outcomes
        testable without a database.

        Deliberately **not** an error when there is nobody to call. A
        receptionist tapping the button on an empty queue has not done
        anything wrong, and answering with a failure would train them to
        ignore failures. `QUEUE_EMPTY` says plainly that nothing
        happened.

        Args:
            had_patient_in_consultation: Whether someone was with the
                clinician when the button was pressed.
            has_next_waiting: Whether anyone was waiting to be called.

        Returns:
            The outcome the caller should report.
        """
        if has_next_waiting:
            return AdvanceOutcome.CALLED_NEXT
        if had_patient_in_consultation:
            return AdvanceOutcome.COMPLETED_LAST
        return AdvanceOutcome.QUEUE_EMPTY

    def advance_changed_the_queue(self, outcome: AdvanceOutcome) -> bool:
        """Whether `outcome` means anything was actually written.

        Used to decide whether the transaction has changes worth
        committing and whether anyone needs to be told the queue moved —
        a no-op advance should not look, to a client, like the queue
        changed.
        """
        return outcome is not AdvanceOutcome.QUEUE_EMPTY

    # -- Policy ----------------------------------------------------------

    def ensure_clinic_accepts_patients(
        self, *, clinic_id: str, is_accepting_patients: bool
    ) -> None:
        """Guards the one precondition a clinic can refuse a join on.

        Args:
            clinic_id: The clinic being joined, for the error message.
            is_accepting_patients: The clinic's current admission flag.

        Raises:
            ClinicNotAcceptingPatientsError: If the clinic has stopped
                admitting patients.
        """
        if not is_accepting_patients:
            raise ClinicNotAcceptingPatientsError(clinic_id)

    def ensure_not_already_queued(
        self, *, clinic_id: str, user_id: str, holds_active_place: bool
    ) -> None:
        """Guards against one patient holding two places in the same
        queue.

        Whether they already hold one is a fact only Layer 4 can
        establish, so it arrives as a boolean; deciding what that fact
        *means* stays here.

        Args:
            clinic_id: The clinic being joined.
            user_id: The patient joining.
            holds_active_place: Whether this patient already holds an
                active place in this clinic's queue.

        Raises:
            AlreadyInQueueError: If they do.
        """
        if holds_active_place:
            raise AlreadyInQueueError(clinic_id, user_id)

    def ensure_reservation_is_active(
        self, *, reservation_id: str, status: str, active_statuses: tuple[str, ...]
    ) -> None:
        """Guards operations that only make sense on a place still in
        the queue, such as cancelling it.

        Args:
            reservation_id: The reservation being acted on.
            status: Its current status, as a plain string — Layer 3
                does not import Layer 5's enum.
            active_statuses: The statuses that count as still queued.

        Raises:
            ReservationNotActiveError: If `status` is not among
                `active_statuses`.
        """
        if status not in active_statuses:
            raise ReservationNotActiveError(reservation_id, status)
