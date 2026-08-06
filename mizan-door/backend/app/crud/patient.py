import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate


async def create_patient(db: AsyncSession, data: PatientCreate) -> Patient:
    patient = Patient(name=data.name, phone=data.phone)
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


async def get_patient(db: AsyncSession, patient_id: uuid.UUID) -> Patient | None:
    return await db.get(Patient, patient_id)


async def get_patient_by_phone(db: AsyncSession, phone: str) -> Patient | None:
    result = await db.execute(select(Patient).where(Patient.phone == phone))
    return result.scalar_one_or_none()


async def list_patients(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[Patient]:
    result = await db.execute(select(Patient).offset(skip).limit(limit).order_by(Patient.created_at))
    return list(result.scalars().all())


async def update_patient(db: AsyncSession, patient: Patient, data: PatientUpdate) -> Patient:
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(patient, field, value)
    await db.commit()
    await db.refresh(patient)
    return patient


async def delete_patient(db: AsyncSession, patient: Patient) -> None:
    await db.delete(patient)
    await db.commit()
