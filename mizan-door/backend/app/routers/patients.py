import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud import patient as patient_crud
from app.schemas.patient import PatientCreate, PatientRead, PatientUpdate

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.post("/", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
async def create_patient(payload: PatientCreate, db: AsyncSession = Depends(get_db)) -> PatientRead:
    existing = await patient_crud.get_patient_by_phone(db, payload.phone)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Patient with this phone already exists"
        )
    patient = await patient_crud.create_patient(db, payload)
    return PatientRead.model_validate(patient)


@router.get("/", response_model=list[PatientRead])
async def list_patients(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> list[PatientRead]:
    patients = await patient_crud.list_patients(db, skip=skip, limit=limit)
    return [PatientRead.model_validate(p) for p in patients]


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(patient_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PatientRead:
    patient = await patient_crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return PatientRead.model_validate(patient)


@router.patch("/{patient_id}", response_model=PatientRead)
async def update_patient(
    patient_id: uuid.UUID, payload: PatientUpdate, db: AsyncSession = Depends(get_db)
) -> PatientRead:
    patient = await patient_crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    patient = await patient_crud.update_patient(db, patient, payload)
    return PatientRead.model_validate(patient)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(patient_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    patient = await patient_crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    await patient_crud.delete_patient(db, patient)
