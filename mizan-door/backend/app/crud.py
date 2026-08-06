"""Async SQLAlchemy CRUD functions for the Mizan Door API."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clinic import Clinic
from app.models.patient import Patient
from app.models.queue_entry import QueueEntry, QueueStatus
from app.schemas import ClinicCreate, PatientCreate

# Queue entries with one of these statuses are considered part of the
# clinic's "current" (still-in-progress) queue.
ACTIVE_QUEUE_STATUSES = (QueueStatus.WAITING, QueueStatus.IN_CONSULTATION)


def _start_of_today() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Clinic
# ---------------------------------------------------------------------------
async def create_clinic(db: AsyncSession, clinic_in: ClinicCreate) -> Clinic:
    clinic = Clinic(name=clinic_in.name, specialty=clinic_in.specialty)
    db.add(clinic)
    await db.commit()
    await db.refresh(clinic)
    return clinic


async def get_clinic(db: AsyncSession, clinic_id: uuid.UUID) -> Clinic | None:
    return await db.get(Clinic, clinic_id)


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------
async def create_patient(db: AsyncSession, patient_in: PatientCreate) -> Patient:
    patient = Patient(name=patient_in.name, phone=patient_in.phone)
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


async def get_patient(db: AsyncSession, patient_id: uuid.UUID) -> Patient | None:
    return await db.get(Patient, patient_id)


async def get_patient_by_phone(db: AsyncSession, phone: str) -> Patient | None:
    result = await db.execute(select(Patient).where(Patient.phone == phone))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# QueueEntry
# ---------------------------------------------------------------------------
async def add_patient_to_queue(
    db: AsyncSession, clinic_id: uuid.UUID, patient_id: uuid.UUID, is_urgent: bool = False
) -> QueueEntry:
    """Add a patient to a clinic's queue, assigning the next ticket number.

    Ticket numbers are scoped per clinic and reset daily (based on `joined_at`).
    """
    result = await db.execute(
        select(func.max(QueueEntry.queue_number)).where(
            QueueEntry.clinic_id == clinic_id,
            QueueEntry.joined_at >= _start_of_today(),
        )
    )
    next_number = (result.scalar() or 0) + 1

    entry = QueueEntry(
        clinic_id=clinic_id,
        patient_id=patient_id,
        queue_number=next_number,
        is_urgent=is_urgent,
        status=QueueStatus.WAITING,
    )
    db.add(entry)
    await db.commit()

    # Re-fetch with the patient relationship eagerly loaded so the response
    # schema (which nests PatientResponse) can be built without a lazy load.
    result = await db.execute(
        select(QueueEntry).options(selectinload(QueueEntry.patient)).where(QueueEntry.id == entry.id)
    )
    return result.scalar_one()


async def get_clinic_queue(db: AsyncSession, clinic_id: uuid.UUID) -> list[QueueEntry]:
    """Return a clinic's current active queue (waiting/in_consultation), urgent first."""
    result = await db.execute(
        select(QueueEntry)
        .options(selectinload(QueueEntry.patient))
        .where(
            QueueEntry.clinic_id == clinic_id,
            QueueEntry.status.in_(ACTIVE_QUEUE_STATUSES),
        )
        .order_by(QueueEntry.is_urgent.desc(), QueueEntry.queue_number.asc())
    )
    return list(result.scalars().all())


async def advance_queue(db: AsyncSession, clinic_id: uuid.UUID) -> None:
    """Call the next patient: complete the current consultation and promote the next one.

    - Whoever is currently `in_consultation` for this clinic is marked `completed`.
    - The next `waiting` patient (urgent first, then by `queue_number`) is
      promoted to `in_consultation`.

    If there is no one currently in consultation, only the promotion happens
    (this is the "start of day" / first call case). If there is no one
    waiting, only the completion happens.
    """
    current_result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.clinic_id == clinic_id,
            QueueEntry.status == QueueStatus.IN_CONSULTATION,
        )
    )
    current_entry = current_result.scalars().first()
    if current_entry is not None:
        current_entry.status = QueueStatus.COMPLETED

    next_result = await db.execute(
        select(QueueEntry)
        .where(
            QueueEntry.clinic_id == clinic_id,
            QueueEntry.status == QueueStatus.WAITING,
        )
        .order_by(QueueEntry.is_urgent.desc(), QueueEntry.queue_number.asc())
        .limit(1)
    )
    next_entry = next_result.scalars().first()
    if next_entry is not None:
        next_entry.status = QueueStatus.IN_CONSULTATION

    await db.commit()
