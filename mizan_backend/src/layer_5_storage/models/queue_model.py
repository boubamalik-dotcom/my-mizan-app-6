"""Layer 5 — SQLAlchemy ORM models for Mizan Door's clinic queues.

STRICT RULE: this module contains ORM models only. It has zero imports
from Layers 2, 3, or 4 — it knows nothing about business rules, HTTP,
or how it is accessed. `layer_4_data_access/repositories/
queue_repository.py` is the only code elsewhere in the backend that
imports these models, and it alone translates rows here into plain
data that Layers 2/3 can consume.

Pessimistic concurrency control, unlike the wallet: assigning the next
ticket number is a *read-then-insert* against rows the reader does not
own, so `WalletModel`'s optimistic `version_id_col` has nothing to
guard. Two patients joining the same clinic in the same millisecond
would both read ``MAX(position) = 7`` and both insert ``8``. The
defence is layered:

1. `QueueRepository.join_queue` takes a ``SELECT ... FOR UPDATE`` row
   lock on the **clinic** before reading the highest ticket, so joins
   for one clinic are serialised (joins for *different* clinics still
   run in parallel, since they lock different rows).
2. ``uq_reservation_clinic_position`` below makes the guarantee
   structural rather than merely procedural: even a future code path
   that forgets the lock cannot persist a duplicate ticket, it gets an
   `IntegrityError` instead. A uniqueness rule that only holds while
   every caller remembers to do something is not a uniqueness rule.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base_model import Base, TimestampMixin, generate_uuid

#: Used when a clinic is created without an explicit specialty. Arabic
#: because it is displayed verbatim by `mizan_frontend`, which has no
#: translation layer for clinic metadata.
DEFAULT_SPECIALTY = "طب عام"

#: Fallback pace for a clinic that has not measured its own, in
#: minutes per patient. Only a seed value — a clinic is expected to
#: tune it.
DEFAULT_SERVICE_RATE_MINUTES = 10


class ReservationStatus(str, enum.Enum):
    """The lifecycle of one patient's place in a queue.

    Stored as its lowercase *value* (see ``values_callable`` on the
    column) rather than the enum member name, so the column reads
    ``'waiting'`` in the database and in the API alike, and a plain SQL
    query written by a clinic administrator matches what the JSON
    shows.

    Duplicated here rather than imported from Layer 3 for the same
    reason `MessageType` is: Layer 5 may not import Layer 3.
    `tests/test_layer_isolation.py` keeps the two definitions in sync.
    """

    #: Holding a place in line, not yet called.
    WAITING = "waiting"
    #: Called in and currently with the clinician. Still occupies a
    #: place in the queue — the patient has not left yet, and everyone
    #: behind them is still behind them.
    IN_CONSULTATION = "in_consultation"
    #: Seen by the clinic. Terminal.
    SERVED = "served"
    #: Given up, by the patient or the clinic. Terminal.
    CANCELLED = "cancelled"


#: The statuses that occupy a place in the queue.
#:
#: `IN_CONSULTATION` counts as occupying a place deliberately: a patient
#: in the room is still ahead of everyone waiting, so excluding them
#: would move every remaining patient up a place the moment the
#: clinician called someone in — telling the whole waiting room they had
#: advanced when nothing had actually finished.
ACTIVE_STATUSES = (ReservationStatus.WAITING, ReservationStatus.IN_CONSULTATION)

#: The statuses a reservation can never leave.
TERMINAL_STATUSES = (ReservationStatus.SERVED, ReservationStatus.CANCELLED)


class ClinicModel(Base, TimestampMixin):
    """A clinic that runs a virtual waiting queue.

    ``service_rate_minutes`` is how long this clinic currently takes
    per patient. It is the *only* input the wait-time estimate has
    beyond queue length, which is why it lives on the clinic rather
    than being hardcoded: a dentist averaging 15 minutes and a general
    practitioner averaging 8 produce very different estimates from the
    same queue length.

    ``is_accepting_patients`` is deliberately separate from deleting
    the clinic. A clinic that has stopped admitting people for the day
    still has a queue worth showing, so a patient can see *why* they
    cannot join rather than watching the clinic vanish from the list.
    """

    __tablename__ = "clinics"
    __table_args__ = (
        CheckConstraint(
            "service_rate_minutes > 0", name="ck_clinic_service_rate_positive"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    #: Displayed beneath the clinic name. Not nullable with a default
    #: rather than nullable: the frontend renders this string directly,
    #: and "no specialty" has no sensible rendering.
    specialty: Mapped[str] = mapped_column(
        String(100), nullable=False, default=DEFAULT_SPECIALTY
    )
    #: Neighbourhood, shown alongside the specialty. Empty string
    #: rather than NULL for the same reason.
    district: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    service_rate_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_SERVICE_RATE_MINUTES
    )
    is_accepting_patients: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        """Compact representation for logs/debuggers, not part of any
        public API contract."""
        return (
            f"ClinicModel(id={self.id!r}, name={self.name!r}, "
            f"is_accepting_patients={self.is_accepting_patients!r})"
        )


class ReservationModel(Base, TimestampMixin):
    """One patient's place in one clinic's queue.

    ``position`` is the **ticket number**: a per-clinic counter that
    only ever increases, assigned once at join time and never rewritten
    afterwards. It is deliberately *not* "how many people are ahead of
    you" — that figure changes every time anyone ahead is served, so
    storing it would mean updating every waiting row on each
    consultation, and any missed update would leave the queue lying
    about itself. The displayed position is derived at read time by
    counting active tickets with a lower number, which cannot drift
    because there is nothing to keep in sync.

    ``uq_reservation_clinic_position`` therefore does double duty: it
    is the structural guarantee that no two patients hold the same
    ticket in the same clinic, and it is what makes the derived
    position unambiguous.
    """

    __tablename__ = "queue_reservations"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "position", name="uq_reservation_clinic_position"
        ),
        CheckConstraint("position > 0", name="ck_reservation_position_positive"),
        # The two queries this table exists to serve: "how long is
        # clinic X's queue" and "where am I". Both filter on status, so
        # it is part of each index rather than a separate one.
        Index("ix_reservation_clinic_status", "clinic_id", "status"),
        Index("ix_reservation_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id"), nullable=False, index=True
    )
    #: A real foreign key into ``users.id``: a reservation belongs to a
    #: registered account, which is what lets `QueueController` enforce
    #: "you may only cancel your own place".
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    #: The immutable ticket number described in the class docstring.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[ReservationStatus] = mapped_column(
        SqlEnum(
            ReservationStatus,
            name="reservation_status",
            native_enum=False,
            # Stores 'waiting' rather than 'WAITING'; see the enum's
            # docstring.
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        nullable=False,
        default=ReservationStatus.WAITING,
    )

    #: When the clinic called this patient in — the moment the status
    #: became `IN_CONSULTATION`. Null while they are still waiting, and
    #: null forever for anyone who cancelled before being called.
    called_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: When the reservation reached a terminal status, whether that was
    #: `SERVED` or `CANCELLED`.
    #:
    #: Recorded separately from `updated_at`, which any future edit
    #: would overwrite. These two columns are what make a clinic's day
    #: measurable after the fact — how long people actually waited
    #: (`called_at - created_at`) and how long consultations actually
    #: took (`completed_at - called_at`) — which is the only honest way
    #: to tune `ClinicModel.service_rate_minutes` away from its
    #: guessed default.
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        """Compact representation for logs/debuggers, not part of any
        public API contract."""
        return (
            f"ReservationModel(id={self.id!r}, clinic_id={self.clinic_id!r}, "
            f"position={self.position!r}, status={self.status!r})"
        )
