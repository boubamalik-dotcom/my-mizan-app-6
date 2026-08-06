import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud import clinic as clinic_crud
from app.schemas.clinic import ClinicCreate, ClinicRead, ClinicUpdate

router = APIRouter(prefix="/api/v1/clinics", tags=["clinics"])


@router.post("/", response_model=ClinicRead, status_code=status.HTTP_201_CREATED)
async def create_clinic(payload: ClinicCreate, db: AsyncSession = Depends(get_db)) -> ClinicRead:
    clinic = await clinic_crud.create_clinic(db, payload)
    return ClinicRead.model_validate(clinic)


@router.get("/", response_model=list[ClinicRead])
async def list_clinics(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> list[ClinicRead]:
    clinics = await clinic_crud.list_clinics(db, skip=skip, limit=limit)
    return [ClinicRead.model_validate(c) for c in clinics]


@router.get("/{clinic_id}", response_model=ClinicRead)
async def get_clinic(clinic_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ClinicRead:
    clinic = await clinic_crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    return ClinicRead.model_validate(clinic)


@router.patch("/{clinic_id}", response_model=ClinicRead)
async def update_clinic(
    clinic_id: uuid.UUID, payload: ClinicUpdate, db: AsyncSession = Depends(get_db)
) -> ClinicRead:
    clinic = await clinic_crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    clinic = await clinic_crud.update_clinic(db, clinic, payload)
    return ClinicRead.model_validate(clinic)


@router.delete("/{clinic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clinic(clinic_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    clinic = await clinic_crud.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found")
    await clinic_crud.delete_clinic(db, clinic)
