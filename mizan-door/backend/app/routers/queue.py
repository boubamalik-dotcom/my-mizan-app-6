import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud import clinic as clinic_crud
from app.crud import patient as patient_crud
from app.crud import queue_entry as queue_crud
from app.models.queue_entry import QueueEntry
from app.schemas.queue_entry import (
    QueueEntryCreate,
    QueueEntryRead,
    QueueEntryUpdate,
    QueueEntryWithPatient,
)

router = APIRouter(prefix="/api/v1/queue", tags=["queue"])


def _to_with_patient(entry: QueueEntry) -> QueueEntryWithPatient:
    return QueueEntryWithPatient(
        id=entry.id,
        clinic_id=entry.clinic_id,
        patient_id=entry.patient_id,
        queue_number=entry.queue_number,
        status=entry.status,
        is_urgent=entry.is_urgent,
        joined_at=entry.joined_at,
        patient_name=entry.patient.name,
        patient_phone=entry.patient.phone,
    )


@router.post("/", response_model=QueueEntryRead, status_code=status.HTTP_201_CREATED)
async def join_queue(payload: QueueEntryCreate, db: AsyncSession = Depends(get_db)) -> QueueEntryRead:
    clinic = await clinic_crud.get_clinic(db, payload.clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    patient = await patient_crud.get_patient(db, payload.patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    entry = await queue_crud.create_queue_entry(db, payload)
    return QueueEntryRead.model_validate(entry)


@router.get("/clinic/{clinic_id}", response_model=list[QueueEntryWithPatient])
async def list_clinic_queue(
    clinic_id: uuid.UUID, today_only: bool = True, db: AsyncSession = Depends(get_db)
) -> list[QueueEntryWithPatient]:
    clinic = await clinic_crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")

    entries = await queue_crud.list_queue_entries_for_clinic(db, clinic_id, today_only=today_only)
    return [_to_with_patient(entry) for entry in entries]


@router.get("/{entry_id}", response_model=QueueEntryWithPatient)
async def get_queue_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> QueueEntryWithPatient:
    entry = await queue_crud.get_queue_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue entry not found")
    return _to_with_patient(entry)


@router.patch("/{entry_id}", response_model=QueueEntryWithPatient)
async def update_queue_entry(
    entry_id: uuid.UUID, payload: QueueEntryUpdate, db: AsyncSession = Depends(get_db)
) -> QueueEntryWithPatient:
    entry = await queue_crud.get_queue_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue entry not found")
    entry = await queue_crud.update_queue_entry(db, entry, payload)
    entry = await queue_crud.get_queue_entry(db, entry.id)
    return _to_with_patient(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_queue_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    entry = await queue_crud.get_queue_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue entry not found")
    await queue_crud.delete_queue_entry(db, entry)
