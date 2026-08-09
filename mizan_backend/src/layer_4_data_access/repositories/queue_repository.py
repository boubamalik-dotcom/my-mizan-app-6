"""Layer 4 — async repository abstracting SQLAlchemy-based clinic-queue
persistence for Mizan Door.

Like `wallet_repository.py`, this is the only place besides Layer 5
itself that imports `ClinicModel`/`ReservationModel` or touches an
`AsyncSession`. Layers 2 and 3 only ever see the plain
`ClinicQueueRecord`/`ReservationRecord` dataclasses returned here.

**The concurrency problem this module exists to solve.** Handing out a
ticket number is a read-then-insert: read the highest ticket a clinic
has issued, add one, insert. Two patients tapping "join" in the same
millisecond both read ``7`` and both try to insert ``8``. The wallet's
optimistic `version_id_col` is no help — there is no existing row being
updated whose version could go stale. See `join_queue` for the fix.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...layer_3_business.queue.queue_service import AdvanceOutcome, QueueService
from ...layer_5_storage.base_model import utcnow
from ...layer_5_storage.models.queue_model import (
    ACTIVE_STATUSES,
    ClinicModel,
    ReservationModel,
    ReservationStatus,
)

#: Layer 3's queue rules. Stateless and free of I/O, so a module-level
#: instance is the whole object — the same pattern `deps.py` uses for
#: `AuthorizationService`. Layer 4 importing Layer 3 is the permitted
#: direction (`tests/test_layer_isolation.py`); the reverse is not.
_rules = QueueService()

#: Tickets still to be called. Counts `WAITING` only, so the figure
#: means "people yet to be seen" rather than lumping in whoever is
#: already in the room.
_WAITING_COUNT = func.count(
    case((ReservationModel.status == ReservationStatus.WAITING, 1))
).label("waiting_count")

#: The ticket currently with the clinician, or `NULL` when the room is
#: free. `MAX` over a single-row-or-empty set: `ACTIVE_STATUSES`
#: contains exactly one in-consultation ticket per clinic, so the
#: aggregate is just a way to pick it out in the same grouped query as
#: the count.
_NOW_SERVING_TICKET = func.max(
    case(
        (
            ReservationModel.status == ReservationStatus.IN_CONSULTATION,
            ReservationModel.position,
        )
    )
).label("now_serving_ticket")


class QueueRepositoryError(Exception):
    """Base class for every error raised by `QueueRepository`."""


class ClinicNotFoundError(QueueRepositoryError):
    """Raised when an operation references a clinic id that does not
    exist."""

    def __init__(self, clinic_id: str) -> None:
        """
        Args:
            clinic_id: The identifier that could not be resolved.
        """
        self.clinic_id = clinic_id
        super().__init__(f'Clinic "{clinic_id}" does not exist.')


class ReservationNotFoundError(QueueRepositoryError):
    """Raised when an operation references a reservation id that does
    not exist."""

    def __init__(self, reservation_id: str) -> None:
        """
        Args:
            reservation_id: The identifier that could not be resolved.
        """
        self.reservation_id = reservation_id
        super().__init__(f'Reservation "{reservation_id}" does not exist.')


class TicketNumberCollisionError(QueueRepositoryError):
    """Raised when an insert lost the race for a ticket number — i.e.
    ``uq_reservation_clinic_position`` rejected it.

    Should be unreachable while `join_queue`'s row lock is in place;
    it exists because "should be unreachable" is not the same as "is",
    and a duplicate ticket must fail loudly rather than be persisted.
    A caller may simply retry.
    """

    def __init__(self, clinic_id: str, position: int) -> None:
        """
        Args:
            clinic_id: The clinic whose ticket collided.
            position: The ticket number that was already taken.
        """
        self.clinic_id = clinic_id
        self.position = position
        super().__init__(
            f'Ticket {position} was already issued by clinic "{clinic_id}"; '
            "this reservation was rejected. Retry the request."
        )


@dataclass(frozen=True, slots=True)
class ClinicQueueRecord:
    """A clinic together with the current state of its queue —
    everything `GET /queues` needs about one clinic, in one immutable
    snapshot."""

    id: str
    name: str
    specialty: str
    district: str
    service_rate_minutes: int
    is_accepting_patients: bool

    #: Tickets in `WAITING` — people in the room are counted by
    #: `now_serving_ticket` instead, because "3 waiting" should mean
    #: three people still to be called, not two plus one already being
    #: seen.
    waiting_count: int

    #: The ticket currently with the clinician, or `None` if the room is
    #: free. This is the "now serving 42" figure a waiting-room display
    #: exists to show.
    now_serving_ticket: Optional[int] = None


@dataclass(frozen=True, slots=True)
class QueueAdvanceRecord:
    """The result of calling the next patient.

    Carries both sides of the transition, because a clinician needs to
    see the patient who just finished as well as the one now called —
    and because a client that only learned about the new arrival could
    not tell whether the previous consultation ended or was skipped.
    """

    #: What the advance amounted to, decided by Layer 3.
    outcome: AdvanceOutcome
    #: The patient just called in, if any.
    now_serving: Optional["ReservationRecord"]
    #: The patient whose consultation was just completed, if any.
    completed: Optional["ReservationRecord"]
    #: The clinic's queue as it stands after the advance.
    queue: ClinicQueueRecord


@dataclass(frozen=True, slots=True)
class ReservationRecord:
    """An immutable snapshot of one patient's place in a queue.

    Carries both numbers deliberately, because they answer different
    questions and are easy to confuse:

    * `ticket_number` is the immutable per-clinic counter stored in the
      database (`ReservationModel.position`).
    * `people_ahead` is derived at read time by counting active tickets
      below it, and shrinks as the queue moves.
    """

    id: str
    clinic_id: str
    clinic_name: str
    user_id: str
    ticket_number: int
    people_ahead: int
    estimated_wait_minutes: int
    status: ReservationStatus
    created_at: datetime
    #: When the clinic called this patient in; `None` until they are.
    called_at: Optional[datetime] = None
    #: When the reservation was served or cancelled; `None` while active.
    completed_at: Optional[datetime] = None

    @property
    def is_in_consultation(self) -> bool:
        """Whether this patient is with the clinician right now."""
        return self.status is ReservationStatus.IN_CONSULTATION


class QueueRepository:
    """Async repository for clinics and their queue reservations.

    Bound to a single `AsyncSession` for its lifetime — typically one
    per `UnitOfWork` transaction — so every read/write participates in
    that one atomic transaction. That is not incidental here: the row
    lock `join_queue` takes is held until *that* transaction commits,
    so the lock and the insert it protects must share a session.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: The `AsyncSession` this repository will use for
                every operation. Its transaction boundary (commit or
                rollback) is owned by the caller, not by this class.
        """
        self._session = session

    # -- Reads ------------------------------------------------------------

    async def get_clinics_with_queue_status(self) -> list[ClinicQueueRecord]:
        """Returns every clinic alongside how many people are currently
        waiting in it.

        One query with a ``LEFT OUTER JOIN`` and a filtered
        ``COUNT``, not a count per clinic: the N+1 version is
        indistinguishable at four seed clinics and falls over at four
        hundred.

        The join is filtered on active statuses *in the ``ON`` clause*
        rather than in ``WHERE``. With the filter in ``WHERE``, a
        clinic whose reservations are all cancelled would have no
        surviving rows and would drop out of the result entirely —
        an empty clinic would silently disappear from the list instead
        of showing a queue of zero.

        Returns:
            One `ClinicQueueRecord` per clinic, ordered by name so the
            list is stable between requests rather than reordering
            itself on every refresh.
        """
        statement = (
            select(ClinicModel, _WAITING_COUNT, _NOW_SERVING_TICKET)
            .outerjoin(
                ReservationModel,
                (ReservationModel.clinic_id == ClinicModel.id)
                & (ReservationModel.status.in_(ACTIVE_STATUSES)),
            )
            .group_by(ClinicModel.id)
            .order_by(ClinicModel.name.asc())
        )

        result = await self._session.execute(statement)
        return [
            self._to_clinic_queue_record(clinic, count, now_serving)
            for clinic, count, now_serving in result.all()
        ]

    async def get_clinic_queue_status(self, clinic_id: str) -> ClinicQueueRecord:
        """The queue figures for one clinic.

        The single-clinic read `get_clinics_with_queue_status` does for
        all of them, for a caller that has just changed one queue and
        needs to announce its new state without re-reading every other
        clinic in the country.

        Args:
            clinic_id: The clinic to describe.

        Returns:
            Its current `ClinicQueueRecord`.

        Raises:
            ClinicNotFoundError: If `clinic_id` does not exist.
        """
        clinic = await self._session.get(ClinicModel, clinic_id)
        if clinic is None:
            raise ClinicNotFoundError(clinic_id)
        return await self._clinic_queue_snapshot(clinic)

    async def get_active_reservation_for_user(
        self, user_id: str
    ) -> Optional[ReservationRecord]:
        """Fetches the caller's own active place in a queue, if they
        hold one.

        Returns the most recently taken if somehow more than one exists
        (`join_queue` prevents a second in the *same* clinic; nothing
        stops a patient queueing at two different clinics, which is
        legitimate). The frontend shows a single "your turn" banner, so
        it gets the newest.

        Args:
            user_id: The patient.

        Returns:
            A `ReservationRecord`, or `None` if they hold no active
            place.
        """
        statement = (
            select(ReservationModel)
            .where(
                ReservationModel.user_id == user_id,
                ReservationModel.status.in_(ACTIVE_STATUSES),
            )
            .order_by(ReservationModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(statement)
        reservation = result.scalar_one_or_none()
        if reservation is None:
            return None
        return await self._hydrate(reservation)

    async def get_reservation_by_id(
        self, reservation_id: str
    ) -> Optional[ReservationRecord]:
        """Fetches a single reservation by id, for the ownership check
        `QueueController` performs before cancelling it.

        Args:
            reservation_id: The reservation's identifier.

        Returns:
            A `ReservationRecord`, or `None` if no such reservation
            exists.
        """
        reservation = await self._session.get(ReservationModel, reservation_id)
        if reservation is None:
            return None
        return await self._hydrate(reservation)

    # -- Writes -----------------------------------------------------------

    async def join_queue(self, *, clinic_id: str, user_id: str) -> ReservationRecord:
        """Atomically takes the next place in `clinic_id`'s queue for
        `user_id`.

        **The concurrency guarantee.** The first statement is a
        ``SELECT ... FOR UPDATE`` against the clinic's own row::

            SELECT * FROM clinics WHERE id = :clinic_id FOR UPDATE

        On Postgres that takes an exclusive row lock held until this
        transaction commits or rolls back. A second transaction
        reaching the same statement blocks there — before it can read
        the highest ticket — and resumes only once the first has
        committed its insert, so it reads a maximum that already
        includes the ticket just issued. Two patients joining in the
        same millisecond therefore receive ``8`` and ``9``, never
        ``8`` twice.

        The lock is on the **clinic**, not the table, so joins at
        different clinics never wait on each other; only genuine
        contention for the same queue is serialised.

        Two safeguards sit behind it. ``uq_reservation_clinic_position``
        rejects a duplicate ticket outright, surfacing here as
        `TicketNumberCollisionError` rather than a corrupt queue — so
        the guarantee does not rest on every future caller remembering
        to lock. And because the duplicate-place check below runs
        inside the same lock, two simultaneous taps from one patient
        cannot both pass it.

        SQLite ignores ``FOR UPDATE`` (it has no row-level locks and
        serialises writers anyway), so the clause is a no-op there and
        the unique constraint carries the guarantee. That is why the
        genuine multi-connection proof lives in
        `tests/integration_tests/test_queue_concurrency.py`, against a
        real Postgres server.

        Args:
            clinic_id: The clinic to queue at.
            user_id: The patient joining.

        Returns:
            A `ReservationRecord` for the newly held place, including
            the ticket issued and how many people are ahead of it.

        Raises:
            ClinicNotFoundError: If `clinic_id` does not exist.
            ClinicNotAcceptingPatientsError: If the clinic has stopped
                admitting patients (Layer 3 rule).
            AlreadyInQueueError: If this patient already holds an
                active place in this clinic (Layer 3 rule).
            TicketNumberCollisionError: If the unique constraint
                rejected the ticket anyway; retry.
        """
        clinic = await self._lock_clinic(clinic_id)

        # Both rules are evaluated *inside* the lock. Checking whether
        # the clinic is still admitting patients outside it would allow
        # a join to slip past a clinic that closed a moment earlier,
        # and checking for an existing place outside it would let one
        # patient's two simultaneous taps both find nothing.
        _rules.ensure_clinic_accepts_patients(
            clinic_id=clinic_id,
            is_accepting_patients=clinic.is_accepting_patients,
        )
        _rules.ensure_not_already_queued(
            clinic_id=clinic_id,
            user_id=user_id,
            holds_active_place=await self._holds_active_place(
                clinic_id=clinic_id, user_id=user_id
            ),
        )

        highest_issued = await self._session.scalar(
            select(func.max(ReservationModel.position)).where(
                ReservationModel.clinic_id == clinic_id
            )
        )
        position = _rules.next_ticket_number(highest_issued)

        reservation = ReservationModel(
            clinic_id=clinic_id,
            user_id=user_id,
            position=position,
            status=ReservationStatus.WAITING,
        )
        self._session.add(reservation)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise TicketNumberCollisionError(clinic_id, position) from exc

        return await self._hydrate(reservation, clinic=clinic)

    async def advance_clinic_queue(self, clinic_id: str) -> QueueAdvanceRecord:
        """Calls the next patient: completes the current consultation
        and admits whoever is at the front of the line.

        **The concurrency guarantee**, and the reason this is one method
        rather than three. It opens with the same
        ``SELECT ... FOR UPDATE`` lock on the clinic row that
        `join_queue` takes, held until the transaction commits, which
        buys three separate things:

        1. Two receptionists pressing the button at the same instant are
           serialised. Without the lock both read the same "next
           waiting" row and both promote it, so two clicks advance the
           queue by one patient and the second click silently vanishes —
           the clinician presses again, nothing happens, and the room
           waits. (This is not hypothetical: it is exactly how the
           unlocked implementation on
           `cursor/mizan-door-backend-setup-1fc8` behaves — three
           simultaneous clicks there produced a single promotion.)
        2. It cannot interleave with a `join_queue` for the same clinic,
           so nobody is admitted between reading the front of the line
           and promoting it.
        3. It serialises with itself across *processes*, not just
           `asyncio` tasks, because the lock lives in the database
           rather than in this one worker.

        Every patient found in `IN_CONSULTATION` is completed, not just
        the first. Normally there is exactly one; sweeping them all
        means that if the invariant were ever broken — by a manual
        `UPDATE`, say — the queue heals on the next advance instead of
        wedging forever behind a patient who never leaves.

        Args:
            clinic_id: The clinic whose queue to advance.

        Returns:
            A `QueueAdvanceRecord` describing what happened, including
            the clinic's queue afterwards.

        Raises:
            ClinicNotFoundError: If `clinic_id` does not exist.
        """
        clinic = await self._lock_clinic(clinic_id)

        completing = list(
            (
                await self._session.execute(
                    select(ReservationModel)
                    .where(
                        ReservationModel.clinic_id == clinic_id,
                        ReservationModel.status
                        == ReservationStatus.IN_CONSULTATION,
                    )
                    .order_by(ReservationModel.position.asc())
                )
            )
            .scalars()
            .all()
        )

        next_waiting = (
            await self._session.execute(
                select(ReservationModel)
                .where(
                    ReservationModel.clinic_id == clinic_id,
                    ReservationModel.status == ReservationStatus.WAITING,
                )
                # Ticket order is the queue's promise to the room: the
                # lowest outstanding ticket is next, always.
                .order_by(ReservationModel.position.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

        outcome = _rules.classify_advance(
            had_patient_in_consultation=bool(completing),
            has_next_waiting=next_waiting is not None,
        )

        now = utcnow()
        for reservation in completing:
            reservation.status = ReservationStatus.SERVED
            reservation.completed_at = now

        if next_waiting is not None:
            next_waiting.status = ReservationStatus.IN_CONSULTATION
            next_waiting.called_at = now

        if _rules.advance_changed_the_queue(outcome):
            await self._session.flush()

        # Hydrated after the flush so the derived positions and the
        # queue counts describe the state the caller is being handed,
        # not the one that existed before the button was pressed.
        return QueueAdvanceRecord(
            outcome=outcome,
            now_serving=(
                await self._hydrate(next_waiting, clinic=clinic)
                if next_waiting is not None
                else None
            ),
            completed=(
                await self._hydrate(completing[0], clinic=clinic)
                if completing
                else None
            ),
            queue=await self._clinic_queue_snapshot(clinic),
        )

    async def cancel_reservation(self, reservation_id: str) -> ReservationRecord:
        """Gives up a place in a queue, leaving the row in place with a
        terminal status.

        Marked cancelled rather than deleted: the ticket number must
        stay issued so it is never handed to anyone else, and a clinic
        auditing its day needs to see that someone left rather than
        finding a gap in the numbering with no explanation.

        Args:
            reservation_id: The reservation to cancel.

        Returns:
            A `ReservationRecord` reflecting the cancelled status.

        Raises:
            ReservationNotFoundError: If `reservation_id` does not
                exist.
            ReservationNotActiveError: If it was already served or
                cancelled (Layer 3 rule).
        """
        reservation = await self._session.get(ReservationModel, reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)

        _rules.ensure_reservation_is_active(
            reservation_id=reservation_id,
            status=reservation.status.value,
            active_statuses=tuple(status.value for status in ACTIVE_STATUSES),
        )

        reservation.status = ReservationStatus.CANCELLED
        reservation.completed_at = utcnow()
        await self._session.flush()
        return await self._hydrate(reservation)

    async def create_clinic(
        self,
        *,
        name: str,
        specialty: str,
        district: str,
        service_rate_minutes: int,
        is_accepting_patients: bool = True,
    ) -> ClinicQueueRecord:
        """Registers a clinic. Used by the seed script and by tests;
        there is no HTTP endpoint for it yet, since onboarding a clinic
        is an administrative act rather than something the patient app
        does.

        Args:
            name: The clinic's display name.
            specialty: Its medical specialty.
            district: Its neighbourhood.
            service_rate_minutes: Minutes it currently takes per
                patient.
            is_accepting_patients: Whether it is admitting patients.

        Returns:
            A `ClinicQueueRecord` for the new clinic, with an empty
            queue.
        """
        clinic = ClinicModel(
            name=name,
            specialty=specialty,
            district=district,
            service_rate_minutes=service_rate_minutes,
            is_accepting_patients=is_accepting_patients,
        )
        self._session.add(clinic)
        await self._session.flush()
        return self._to_clinic_queue_record(clinic, 0)

    # -- Internal helpers -------------------------------------------------

    async def _lock_clinic(self, clinic_id: str) -> ClinicModel:
        """Takes the exclusive row lock described in `join_queue`, and
        returns the locked clinic.

        Raises:
            ClinicNotFoundError: If no such clinic exists.
        """
        statement = (
            select(ClinicModel).where(ClinicModel.id == clinic_id).with_for_update()
        )
        result = await self._session.execute(statement)
        clinic = result.scalar_one_or_none()
        if clinic is None:
            raise ClinicNotFoundError(clinic_id)
        return clinic

    async def _holds_active_place(self, *, clinic_id: str, user_id: str) -> bool:
        """Whether `user_id` already holds an active place in
        `clinic_id`'s queue."""
        statement = (
            select(ReservationModel.id)
            .where(
                ReservationModel.clinic_id == clinic_id,
                ReservationModel.user_id == user_id,
                ReservationModel.status.in_(ACTIVE_STATUSES),
            )
            .limit(1)
        )
        return await self._session.scalar(statement) is not None

    async def _count_people_ahead(self, reservation: ReservationModel) -> int:
        """Counts active tickets in the same clinic below this one.

        This is what makes the displayed position self-correcting: it
        is recomputed from the tickets that are actually still waiting,
        so serving or cancelling anyone ahead moves the patient up
        without a single stored row being rewritten.
        """
        statement = select(func.count(ReservationModel.id)).where(
            ReservationModel.clinic_id == reservation.clinic_id,
            ReservationModel.status.in_(ACTIVE_STATUSES),
            ReservationModel.position < reservation.position,
        )
        return int(await self._session.scalar(statement) or 0)

    async def _hydrate(
        self,
        reservation: ReservationModel,
        *,
        clinic: Optional[ClinicModel] = None,
    ) -> ReservationRecord:
        """Builds the plain-data record for `reservation`, deriving the
        queue position and wait estimate.

        Args:
            reservation: The persisted row.
            clinic: Its clinic, when the caller already holds it (as
                `join_queue` does, having just locked it) — saves a
                redundant round trip.
        """
        resolved_clinic = clinic or await self._session.get(
            ClinicModel, reservation.clinic_id
        )
        if resolved_clinic is None:  # pragma: no cover - enforced by the FK
            raise ClinicNotFoundError(reservation.clinic_id)

        # A reservation that is no longer active has nobody ahead of it
        # and no wait left to estimate; counting tickets below a
        # cancelled one would report a meaningless queue position.
        is_active = reservation.status in ACTIVE_STATUSES
        people_ahead = await self._count_people_ahead(reservation) if is_active else 0

        return ReservationRecord(
            id=reservation.id,
            clinic_id=reservation.clinic_id,
            clinic_name=resolved_clinic.name,
            user_id=reservation.user_id,
            ticket_number=reservation.position,
            people_ahead=people_ahead,
            estimated_wait_minutes=_rules.estimate_wait_minutes(
                people_ahead=people_ahead,
                service_rate_minutes=resolved_clinic.service_rate_minutes,
            )
            if is_active
            else 0,
            status=reservation.status,
            created_at=self._as_utc(reservation.created_at),
            called_at=self._as_utc(reservation.called_at),
            completed_at=self._as_utc(reservation.completed_at),
        )

    async def _clinic_queue_snapshot(
        self, clinic: ClinicModel
    ) -> ClinicQueueRecord:
        """The queue figures for one already-loaded clinic.

        The single-clinic counterpart of
        `get_clinics_with_queue_status`, for callers that have just
        changed one clinic's queue and need to report its new state
        without re-reading every other clinic in the country.
        """
        row = (
            await self._session.execute(
                select(_WAITING_COUNT, _NOW_SERVING_TICKET).where(
                    ReservationModel.clinic_id == clinic.id,
                    ReservationModel.status.in_(ACTIVE_STATUSES),
                )
            )
        ).one()
        return self._to_clinic_queue_record(clinic, row[0], row[1])

    @staticmethod
    def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
        """Normalises a persisted timestamp to timezone-aware UTC.

        SQLite has no timestamp type that carries an offset, so a value
        read back from it is naive even though the column is declared
        ``DateTime(timezone=True)`` — while a value written moments ago
        and still in the session's identity map is the aware object we
        set. Handing both out unchanged means
        ``completed_at - called_at`` raises *"can't compare
        offset-naive and offset-aware datetimes"* on the development
        database and works on Postgres, which is the worst of both.

        Since everything this layer writes is UTC (`utcnow`), a naive
        value can only be UTC, so labelling it as such loses nothing
        and makes the records comparable everywhere.
        """
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _to_clinic_queue_record(
        clinic: ClinicModel,
        waiting_count: Optional[int],
        now_serving_ticket: Optional[int] = None,
    ) -> ClinicQueueRecord:
        """Maps a `ClinicModel` row plus its queue figures to the
        plain-data `ClinicQueueRecord`."""
        return ClinicQueueRecord(
            id=clinic.id,
            name=clinic.name,
            specialty=clinic.specialty,
            district=clinic.district,
            service_rate_minutes=clinic.service_rate_minutes,
            is_accepting_patients=clinic.is_accepting_patients,
            waiting_count=int(waiting_count or 0),
            now_serving_ticket=(
                int(now_serving_ticket) if now_serving_ticket is not None else None
            ),
        )


#: Re-exported so Layer 2 can catch every queue failure — repository
#: and domain alike — from one import, mirroring how
#: `wallet_controller.py` imports its error types from the repository
#: module rather than reaching across to Layer 3 separately.
__all__: Sequence[str] = (
    "AdvanceOutcome",
    "ClinicNotFoundError",
    "ClinicQueueRecord",
    "QueueAdvanceRecord",
    "QueueRepository",
    "QueueRepositoryError",
    "ReservationNotFoundError",
    "ReservationRecord",
    "ReservationStatus",
    "TicketNumberCollisionError",
)
